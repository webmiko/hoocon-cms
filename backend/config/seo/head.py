"""Build SEO context and rewrite tags in index.html (БЗ M1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from typing import cast

from django.conf import settings

from config.seo.meta_text import (
    DESCRIPTION_MAX_LEN,
    TITLE_PARTIAL_MAX,
    format_branded_title,
    format_meta_description,
    sku_kind_for_title,
    sku_meta_description,
    sku_meta_title_partial,
)
from config.seo.routes import (
    DEFAULT_DESCRIPTION,
    NOINDEX_PREFIXES,
    OG_IMAGE_PATH,
    PUBLIC_STATIC_ROUTES,
    SLUG_RE,
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
    # 410 when the address has no live page and no redirect. 200 for real routes.
    http_status: int = 200
    # Facts and links in the first HTML, inside #root, before the script runs.
    crawl_heading: str = ""
    crawl_lines: tuple[str, ...] = ()
    crawl_links: tuple[tuple[str, str], ...] = ()
    # Absolute path for a 301 when the request address is not canonical.
    redirect_to: str = ""


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


_CRAWL_NAV: tuple[tuple[str, str], ...] = (
    ("/catalog", "Каталог"),
    ("/dokumentaciya", "Документация"),
    ("/statyi", "Статьи"),
    ("/faq", "FAQ"),
    ("/kontakty", "Контакты"),
)
_HOME_CRAWL_HEADING = "Электроприводы для вентиляции и кондиционирования"
_HOME_CRAWL_LINE = (
    "Подбор модели за минуту. Укажите тип продукции и параметры из проекта: привод на заслонку, "
    "шаровой кран, комплект кран+привод или кронштейн BR-M/BR-ML под привод Hoocon. "
    "Сервис покажет подходящие позиции в каталоге."
)
_SHORT_DESCRIPTION_MIN = 80


def lengthen_listing_description(text: str) -> str:
    """Stretch a one-word category blurb into a snippet a search result can use."""
    clean = plain_text_for_meta(text, max_len=DESCRIPTION_MAX_LEN)
    if len(clean) >= _SHORT_DESCRIPTION_MIN:
        return format_meta_description(clean)
    return format_meta_description(
        f"{clean}. Подбор Hoocon по моменту и напряжению, паспорта PDF, запрос КП.",
    )


def news_mirrors_article(slug: str) -> str | None:
    """Return the article path when a news slug is ``article-{article slug}``."""
    if not slug.startswith("article-"):
        return None
    article_slug = slug.removeprefix("article-")
    if not article_slug:
        return None
    from content.models import Article
    from content.views import publicly_visible

    if publicly_visible(Article).filter(slug=article_slug).exists():
        return f"/statyi/{article_slug}"
    return None


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
    body_text = plain_text_for_meta(article.excerpt or article.body or "", max_len=480)
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
        crawl_heading=plain_text_for_meta(article.title, max_len=180),
        crawl_lines=(body_text,) if body_text else (),
        crawl_links=(("/statyi", "Статьи"), ("/catalog", "Каталог")),
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
    mirror = news_mirrors_article(slug)
    body_text = plain_text_for_meta(news.body or news.title, max_len=480)
    canonical = mirror or f"/novosti/{slug}"
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(
            plain_text_for_meta(news.title, max_len=TITLE_PARTIAL_MAX),
        ),
        description=format_meta_description(news.body or news.title),
        noindex=mirror is not None,
        og_type="article",
        article_published_at=published,
        breadcrumb=(
            ("/", "Главная"),
            ("/novosti", "Новости"),
            (canonical, news.title),
        ),
        og_image_url=_absolute_media_url(news.cover),
        crawl_heading=plain_text_for_meta(news.title, max_len=180),
        crawl_lines=(body_text,) if body_text else (),
        crawl_links=((canonical, "Статья"), ("/catalog", "Каталог")) if mirror else _CRAWL_NAV,
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
        crawl_heading=plain_text_for_meta(title, max_len=180),
        crawl_lines=(plain_text_for_meta(desc, max_len=480),),
        crawl_links=_CRAWL_NAV,
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
        analog=(sku.analog_belimo_code or ""),
        kind=sku_kind_for_title(cat_name),
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
    crawl_lines: list[str] = []
    if sku.sku_code:
        crawl_lines.append(f"Артикул {sku.sku_code}")
    for row in highlights[:5]:
        label = (row.get("name") or "").strip()
        value = (row.get("value") or "").strip()
        unit = (row.get("unit") or "").strip()
        if not value:
            continue
        shown = f"{value} {unit}".strip() if unit and unit not in value else value
        crawl_lines.append(f"{label}: {shown}" if label else shown)
    analog_code = (sku.analog_belimo_code or "").strip()
    if analog_code:
        crawl_lines.append(f"Аналог Belimo: {analog_code}")
    from catalog.docs_hub import canonical_pdf_path

    pdf_links: list[tuple[str, str]] = []
    seen_pdf: set[str] = set()
    for pf in sku.files.filter(is_published=True).order_by("sort_order", "title", "id"):
        href = canonical_pdf_path(
            sku_code=sku.sku_code or "",
            title=pf.title,
            file_type=pf.file_type,
        )
        if href in seen_pdf:
            continue
        seen_pdf.add(href)
        pdf_links.append((href, pf.title))
    redirect_to = ""
    http_status = 200
    if path.startswith("/catalog/") and path != canonical:
        redirect_to = canonical
        http_status = 301
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(title_partial),
        description=sku_meta_description(
            sku.sku_code or sku.slug,
            category_name=cat_name,
            moment=by_key.get("moment", ""),
            voltage=by_key.get("voltage", ""),
            analog=(sku.analog_belimo_code or ""),
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
        crawl_heading=display_name or sku.sku_code or sku.slug,
        crawl_lines=tuple(crawl_lines),
        crawl_links=tuple([*crumbs[:-1], *pdf_links]),
        redirect_to=redirect_to,
        http_status=http_status,
    )


def _resolve_missing_catalog_sku(path: str) -> SeoHeadContext | None:
    """Gone (410) for ``/catalog/{category}/{sku}`` when that SKU is not published."""
    if not path.startswith("/catalog/"):
        return None
    parts = [p for p in path.removeprefix("/catalog/").split("/") if p]
    if len(parts) != 2:
        return None
    cat_slug = validate_slug(parts[0])
    sku_slug = validate_slug(parts[1])
    from catalog.models import SKU

    if SKU.objects.filter(slug=sku_slug, is_published=True).exists():
        return None
    title_partial = plain_text_for_meta(
        f"Товар не найден — {sku_slug}",
        max_len=TITLE_PARTIAL_MAX,
    )
    canonical = f"/catalog/{cat_slug}/{sku_slug}"
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(title_partial),
        description=format_meta_description(
            f"Позиция {sku_slug} не найдена в каталоге Hoocon.",
        ),
        noindex=True,
        http_status=410,
        breadcrumb=(
            ("/", "Главная"),
            ("/catalog", "Каталог"),
            (canonical, sku_slug),
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
    desc = lengthen_listing_description(cat.description or cat.name or DEFAULT_DESCRIPTION)
    name = plain_text_for_meta(cat.name, max_len=TITLE_PARTIAL_MAX)
    if len(name) < 24:
        name = f"{name} для электроприводов"
    from catalog.models import SKU
    from catalog.urls_paths import catalog_path_for_sku

    sku_links = tuple(
        (catalog_path_for_sku(sku), sku.sku_code or sku.slug)
        for sku in SKU.objects.filter(is_published=True, product__category_id=cat.pk)
        .select_related("product__category")
        .order_by("sku_code")[:24]
    )
    return SeoHeadContext(
        canonical_path=canonical,
        page_title=_format_page_title(name),
        description=desc,
        noindex=False,
        breadcrumb=(
            ("/", "Главная"),
            ("/catalog", "Каталог"),
            (canonical, cat.name),
        ),
        crawl_heading=cat.name,
        crawl_lines=(desc,),
        crawl_links=(("/", "Главная"), ("/catalog", "Каталог"), *sku_links),
    )


def _legacy_news_target(path: str) -> str | None:
    """Tilda ``/news/<a>/<b>`` → ``/novosti/<a>-<b>``.

    The SPA joins the same segments. A crawler that does not run JavaScript
    must get this 301 from the first response, not a 410.
    """
    if path == "/news":
        return "/novosti"
    if not path.startswith("/news/"):
        return None
    parts = [part.lower() for part in path.removeprefix("/news/").split("/") if part]
    if not parts:
        return "/novosti"
    slug = "-".join(parts)
    if not slug or len(slug) > 300 or not re.fullmatch(SLUG_RE, slug):
        return None
    return f"/novosti/{slug}"


def resolve_seo_context(raw_path: str) -> SeoHeadContext:
    """Resolve SEO context for a request pathname.

    Args:
        raw_path: Raw request path.

    Returns:
        SeoHeadContext for head injection and JSON-LD.
    """
    path = normalize_spa_path(raw_path)
    legacy_news = _legacy_news_target(path)
    if legacy_news is not None:
        return SeoHeadContext(
            canonical_path=legacy_news,
            page_title=_format_page_title("Новости"),
            description=DEFAULT_DESCRIPTION,
            noindex=True,
            http_status=301,
            redirect_to=legacy_news,
        )

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
        description = format_meta_description(static.get("description", DEFAULT_DESCRIPTION))
        if path == "/":
            crawl_heading = _HOME_CRAWL_HEADING
            crawl_lines = (_HOME_CRAWL_LINE,)
            crawl_links = _CRAWL_NAV
        elif path == "/catalog":
            from catalog.models import Category
            from catalog.urls_paths import catalog_category_path

            crawl_heading = static.get("title") or "Каталог"
            crawl_lines = (description,)
            crawl_links = (
                tuple((catalog_category_path(cat.slug), cat.name) for cat in Category.objects.order_by("name"))
                or _CRAWL_NAV
            )
        else:
            crawl_heading = static.get("title") or ""
            crawl_lines = (description,)
            crawl_links = _CRAWL_NAV
        return SeoHeadContext(
            canonical_path=path,
            page_title=_format_page_title(static.get("title")),
            description=description,
            noindex=False,
            breadcrumb=crumbs,
            crawl_heading=crawl_heading,
            crawl_lines=crawl_lines,
            crawl_links=crawl_links,
        )

    if _is_noindex_path(path):
        titles = {
            "/search": "Поиск по сайту",
            "/consultation": "Запрос консультации и КП",
            "/rfq": "Запрос коммерческого предложения",
            "/replacement": "Подбор аналога Belimo",
            "/compare": "Сравнение моделей",
            "/login": "Вход в кабинет",
            "/register": "Регистрация",
            "/account": "Личный кабинет",
            "/kp": "Ответ на коммерческое предложение",
        }
        title_key = path
        if path.startswith("/account/") or path == "/account":
            title_key = "/account"
        return SeoHeadContext(
            canonical_path=path,
            page_title=_format_page_title(titles.get(title_key)),
            description=DEFAULT_DESCRIPTION,
            noindex=True,
        )

    sku_ctx = _resolve_sku(path)
    if sku_ctx is not None:
        return sku_ctx

    missing_sku_ctx = _resolve_missing_catalog_sku(path)
    if missing_sku_ctx is not None:
        return missing_sku_ctx

    return SeoHeadContext(
        canonical_path=path,
        page_title=_format_page_title("Страница не найдена"),
        description=DEFAULT_DESCRIPTION,
        noindex=True,
        http_status=410,
    )


def _replace_tag(html: str, pattern: str, replacement: str) -> str:
    # Callable replacement: titles come from CMS content, and ``\1`` / ``\g<x>``
    # in a plain replacement string would be parsed as a group reference.
    new_html, count = re.subn(
        pattern,
        lambda _match: replacement,
        html,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
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
    if not blocks:
        return html
    nonce_attr = f' nonce="{escape(nonce, quote=True)}"' if nonce else ""
    scripts = "".join(
        f'<script type="application/ld+json"{nonce_attr}>{_json_for_script(block)}</script>' for block in blocks
    )
    return html.replace("</head>", f"{scripts}\n  </head>", 1)


def _json_for_script(block: dict[str, object]) -> str:
    """JSON safe inside ``<script>``: CMS text with ``</script>`` cannot close it."""
    text = json.dumps(block, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
