"""Build SEO context and rewrite tags in index.html (БЗ M1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import cast

from django.conf import settings

from config.seo.meta_text import (
    TITLE_PARTIAL_MAX,
    format_branded_title,
    format_meta_description,
    sku_meta_description,
    sku_meta_title_partial,
)
from config.seo.routes import (
    DEFAULT_DESCRIPTION,
    NOINDEX_PREFIXES,
    OG_IMAGE_PATH,
    PUBLIC_STATIC_ROUTES,
    YANDEX_VERIFICATION_CONTENT,
)
from config.seo.sanitize import normalize_spa_path, plain_text_for_meta, validate_slug


@dataclass(frozen=True)
class SeoHeadContext:
    """Server-side SEO context for one SPA route."""

    canonical_path: str
    page_title: str
    description: str
    noindex: bool
    og_type: str = "website"
    article_published_at: str | None = None
    sku_code: str | None = None
    sku_price: str | None = None
    price_on_request: bool = True
    in_stock: bool = True
    category_name: str | None = None
    breadcrumb: tuple[tuple[str, str], ...] = ()
    # Absolute og:image when the page has a primary photo; else site default.
    og_image_url: str | None = None


def _absolute_media_url(file_field: object | None) -> str | None:
    """Build absolute SITE_URL + media path from an ImageFieldFile-like object."""
    if file_field is None:
        return None
    try:
        url = str(getattr(file_field, "url", "") or "").strip()
    except ValueError:
        return None
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    path = url if url.startswith("/") else f"/{url}"
    return f"{settings.SITE_URL.rstrip('/')}{path}"


def _format_page_title(partial: str | None) -> str:
    """Delegate to branded title helper (≤60 chars with brand)."""
    return format_branded_title(partial)


def _is_noindex_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in NOINDEX_PREFIXES)


def _resolve_article(path: str) -> SeoHeadContext | None:
    if not path.startswith("/statyi/") or path == "/statyi":
        return None
    slug = validate_slug(path.removeprefix("/statyi/").split("/", 1)[0])
    from content.models import Article
    from content.views import publicly_visible

    article = publicly_visible(Article).filter(slug=slug).first()
    if article is None:
        return None
    published = article.published_at.isoformat() if article.published_at else None
    desc_src = article.excerpt or article.body or article.title
    return SeoHeadContext(
        canonical_path=f"/statyi/{slug}",
        page_title=_format_page_title(
            plain_text_for_meta(article.title, max_len=TITLE_PARTIAL_MAX),
        ),
        description=format_meta_description(desc_src),
        noindex=False,
        og_type="article",
        article_published_at=published,
        breadcrumb=(
            ("/", "Главная"),
            ("/statyi", "Статьи"),
            (f"/statyi/{slug}", article.title),
        ),
        og_image_url=_absolute_media_url(article.cover),
    )


def _resolve_news(path: str) -> SeoHeadContext | None:
    if not path.startswith("/novosti/") or path == "/novosti":
        return None
    slug = validate_slug(path.removeprefix("/novosti/").split("/", 1)[0])
    from content.models import News
    from content.views import publicly_visible

    news = publicly_visible(News).filter(slug=slug).first()
    if news is None:
        return None
    published = news.published_at.isoformat() if news.published_at else None
    return SeoHeadContext(
        canonical_path=f"/novosti/{slug}",
        page_title=_format_page_title(
            plain_text_for_meta(news.title, max_len=TITLE_PARTIAL_MAX),
        ),
        description=format_meta_description(news.body or news.title),
        noindex=False,
        og_type="article",
        article_published_at=published,
        breadcrumb=(
            ("/", "Главная"),
            ("/novosti", "Новости"),
            (f"/novosti/{slug}", news.title),
        ),
        og_image_url=_absolute_media_url(news.cover),
    )


def _resolve_page(path: str) -> SeoHeadContext | None:
    """CMS Page at /<slug> when not a known static-only path with DB override."""
    if path == "/" or path.count("/") != 1:
        return None
    slug = validate_slug(path.lstrip("/"))
    from content.models import Page
    from content.views import publicly_visible

    page = publicly_visible(Page).filter(slug=slug).first()
    if page is None:
        return None
    static = PUBLIC_STATIC_ROUTES.get(path, {})
    title = static.get("title") or page.title
    desc = static.get("description") or page.body or page.title
    return SeoHeadContext(
        canonical_path=path,
        page_title=_format_page_title(
            plain_text_for_meta(title, max_len=TITLE_PARTIAL_MAX),
        ),
        description=format_meta_description(desc),
        noindex=False,
        breadcrumb=(("/", "Главная"), (path, page.title)),
    )


def _resolve_sku(path: str) -> SeoHeadContext | None:
    """Resolve nested ``/catalog/{category}/{sku}`` or legacy ``/{sku}``."""
    from catalog.models import SKU
    from catalog.urls_paths import catalog_category_path, catalog_path_for_sku

    slug: str | None = None

    if path.startswith("/catalog/"):
        parts = [p for p in path.removeprefix("/catalog/").split("/") if p]
        if len(parts) == 2:
            slug = parts[1]
        else:
            return None
    else:
        # Legacy flat /{sku} — still resolve for redirects / soft migration.
        if path == "/" or path.count("/") != 1:
            return None
        if path in PUBLIC_STATIC_ROUTES or _is_noindex_path(path):
            return None
        if path.startswith(("/statyi", "/novosti", "/catalog", "/search")):
            return None
        slug = validate_slug(path.lstrip("/"))

    if not slug:
        return None
    slug = validate_slug(slug)

    sku = SKU.objects.filter(slug=slug, is_published=True).select_related("product__category").first()
    if sku is None:
        return None
    cat = sku.product.category if sku.product_id else None  # type: ignore[attr-defined]
    cat_name = cat.name if cat else None
    canonical = catalog_path_for_sku(sku)
    from catalog.facets import format_sku_heading_name, highlights_for_sku

    display_name = format_sku_heading_name(
        sku.name,
        description=sku.description or "",
        sku_code=sku.sku_code or "",
    )
    from catalog.models import Attribute, Category, Product

    values = list(sku.attribute_values.select_related("attribute"))
    for av in values:
        attr = cast(Attribute, av.attribute)
        attr_slug = (attr.slug or "").casefold()
        if attr_slug.startswith("kvs"):
            display_name = format_sku_heading_name(
                sku.name,
                description=sku.description or "",
                sku_code=sku.sku_code or "",
                kvs=str(av.value).strip(),
            )
            break
    category_slug = ""
    product = cast(Product | None, sku.product) if sku.product_id else None
    if product is not None and product.category_id:
        category = cast(Category, product.category)
        category_slug = category.slug
    highlights = highlights_for_sku(
        values,
        description=sku.description or "",
        sku_code=sku.sku_code or "",
        category_slug=category_slug,
    )
    by_key = {row["key"]: row["value"] for row in highlights}
    title_partial = sku_meta_title_partial(
        sku.sku_code or sku.slug,
        moment=by_key.get("moment", ""),
        voltage=by_key.get("voltage", ""),
    )
    from sitesettings.models import SiteSettings

    show_prices = SiteSettings.load().show_prices_on_site
    price: str | None = None
    on_request = True
    if show_prices and sku.price is not None:
        price = str(sku.price)
        on_request = False
    crumbs: list[tuple[str, str]] = [("/", "Главная"), ("/catalog", "Каталог")]
    if cat is not None:
        crumbs.append((catalog_category_path(cat.slug), cat.name))
    crumbs.append((canonical, display_name))
    # Same gallery as PDP/API: own photos, else family fallback filtered by variant.
    from catalog.serializers import _sku_gallery_images

    gallery = _sku_gallery_images(sku)
    primary_image = gallery[0] if gallery else None
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(title_partial),
        description=sku_meta_description(
            sku.sku_code or sku.slug,
            category_name=cat_name,
        ),
        noindex=False,
        og_type="product",
        sku_code=sku.sku_code or sku.slug,
        sku_price=price,
        price_on_request=on_request,
        in_stock=sku.in_stock,
        category_name=cat_name,
        breadcrumb=tuple(crumbs),
        og_image_url=_absolute_media_url(
            primary_image.image if primary_image is not None else None,
        ),
    )


def _resolve_catalog_category(path: str) -> SeoHeadContext | None:
    """Resolve ``/catalog/{category_slug}`` listing pages."""
    if not path.startswith("/catalog/") or path == "/catalog":
        return None
    parts = [p for p in path.removeprefix("/catalog/").split("/") if p]
    if len(parts) != 1:
        return None
    slug = validate_slug(parts[0])
    from catalog.models import Category
    from catalog.urls_paths import catalog_category_path

    cat = Category.objects.filter(slug=slug).first()
    if cat is None:
        return None
    canonical = catalog_category_path(cat.slug)
    desc = plain_text_for_meta(cat.description or cat.name, max_len=160)
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(
            plain_text_for_meta(cat.name, max_len=TITLE_PARTIAL_MAX),
        ),
        description=format_meta_description(desc or DEFAULT_DESCRIPTION),
        noindex=False,
        breadcrumb=(
            ("/", "Главная"),
            ("/catalog", "Каталог"),
            (canonical, cat.name),
        ),
    )


def resolve_seo_context(raw_path: str) -> SeoHeadContext:
    """Resolve SEO context for a request pathname.

    Args:
        raw_path: Raw request path.

    Returns:
        SeoHeadContext for head injection and JSON-LD.
    """
    path = normalize_spa_path(raw_path)

    # CMS pages before SKU so reserved slugs (company, faq, …) stay content.
    for resolver in (_resolve_article, _resolve_news, _resolve_page):
        resolved = resolver(path)
        if resolved is not None:
            return resolved

    cat_ctx = _resolve_catalog_category(path)
    if cat_ctx is not None:
        return cat_ctx

    static = PUBLIC_STATIC_ROUTES.get(path)
    if static is not None:
        crumbs: tuple[tuple[str, str], ...]
        if path == "/":
            crumbs = (("/", "Главная"),)
        else:
            title = static.get("title") or path
            crumbs = (("/", "Главная"), (path, title))
        return SeoHeadContext(
            canonical_path=path,
            page_title=_format_page_title(static.get("title")),
            description=format_meta_description(
                static.get("description", DEFAULT_DESCRIPTION),
            ),
            noindex=False,
            breadcrumb=crumbs,
        )

    if _is_noindex_path(path):
        titles = {
            "/search": "Поиск по сайту",
            "/consultation": "Запрос консультации и КП",
            "/replacement": "Подбор аналога Belimo",
        }
        return SeoHeadContext(
            canonical_path=path,
            page_title=_format_page_title(titles.get(path)),
            description=DEFAULT_DESCRIPTION,
            noindex=True,
        )

    sku_ctx = _resolve_sku(path)
    if sku_ctx is not None:
        return sku_ctx

    return SeoHeadContext(
        canonical_path=path,
        page_title=_format_page_title("Страница не найдена — 404"),
        description=DEFAULT_DESCRIPTION,
        noindex=True,
    )


def _replace_tag(html: str, pattern: str, replacement: str) -> str:
    new_html, count = re.subn(pattern, replacement, html, count=1, flags=re.IGNORECASE | re.DOTALL)
    return new_html if count else html


def _og_image_url(context: SeoHeadContext) -> str:
    if context.og_image_url:
        return context.og_image_url
    return f"{settings.SITE_URL.rstrip('/')}{OG_IMAGE_PATH}"


def apply_seo_head(html: str, context: SeoHeadContext, *, canonical_url: str) -> str:
    """Replace title, meta, canonical, OG, Twitter, robots in HTML.

    Args:
        html: Raw index.html.
        context: Resolved SEO context.
        canonical_url: Absolute canonical URL.

    Returns:
        HTML with escaped SEO tags applied.
    """
    title = escape(context.page_title)
    description = escape(context.description)
    canonical = escape(canonical_url)
    robots = "noindex, nofollow" if context.noindex else "index, follow"
    og_image = escape(_og_image_url(context))
    og_type = escape(context.og_type)

    html = _replace_tag(html, r"<title>.*?</title>", f"<title>{title}</title>")
    html = _ensure_meta(html, "name", "description", description)
    html = _ensure_meta(html, "name", "robots", robots)
    html = _ensure_meta(
        html,
        "name",
        "yandex-verification",
        escape(YANDEX_VERIFICATION_CONTENT),
    )
    html = _ensure_link_canonical(html, canonical)
    html = _ensure_meta(html, "property", "og:title", title)
    html = _ensure_meta(html, "property", "og:description", description)
    html = _ensure_meta(html, "property", "og:url", canonical)
    html = _ensure_meta(html, "property", "og:type", og_type)
    html = _ensure_meta(html, "property", "og:image", og_image)
    html = _ensure_meta(html, "name", "twitter:card", "summary_large_image")
    html = _ensure_meta(html, "name", "twitter:title", title)
    html = _ensure_meta(html, "name", "twitter:description", description)
    html = _ensure_meta(html, "name", "twitter:image", og_image)

    if not context.noindex:
        hreflang = (
            f'<link rel="alternate" hreflang="ru" href="{canonical}" />\n'
            f'    <link rel="alternate" hreflang="x-default" href="{canonical}" />'
        )
        html = re.sub(
            r'<link\s+rel="alternate"\s+hreflang="[^"]*"\s+href="[^"]*"\s*/?>\s*',
            "",
            html,
            flags=re.IGNORECASE,
        )
        html = html.replace("</head>", f"    {hreflang}\n  </head>", 1)

    return html


def _ensure_meta(html: str, attr: str, name: str, content: str) -> str:
    pattern = rf'<meta\s+{attr}="{re.escape(name)}"\s+content="[^"]*"\s*/?>'
    replacement = f'<meta {attr}="{name}" content="{content}" />'
    if re.search(pattern, html, flags=re.IGNORECASE):
        return _replace_tag(html, pattern, replacement)
    return html.replace("</head>", f"    {replacement}\n  </head>", 1)


def _ensure_link_canonical(html: str, href: str) -> str:
    pattern = r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>'
    replacement = f'<link rel="canonical" href="{href}" />'
    if re.search(pattern, html, flags=re.IGNORECASE):
        return _replace_tag(html, pattern, replacement)
    return html.replace("</head>", f"    {replacement}\n  </head>", 1)


def inject_json_ld(html: str, blocks: list[dict[str, object]], *, nonce: str | None) -> str:
    """Insert JSON-LD script blocks before ``</head>``.

    Args:
        html: HTML document.
        blocks: Whitelisted schema.org objects.
        nonce: Optional CSP nonce for script tags.

    Returns:
        HTML with JSON-LD scripts injected.
    """
    import json

    if not blocks:
        return html
    nonce_attr = f' nonce="{escape(nonce, quote=True)}"' if nonce else ""
    scripts = "".join(
        f'<script type="application/ld+json"{nonce_attr}>{json.dumps(block, ensure_ascii=False)}</script>'
        for block in blocks
    )
    return html.replace("</head>", f"{scripts}\n  </head>", 1)
