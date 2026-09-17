"""Knowledge base for GigaChat — single file ``gigachat_kb.txt`` only."""

from __future__ import annotations

from typing import cast

from config.seo.routes import PUBLIC_STATIC_ROUTES
from content.etl.tilda_articles import strip_html_to_text
from content.models import Article, Page
from content.views import publicly_visible
from supportchat.gigachat.kb_branches import search_kb_context
from supportchat.models import FaqItem

_MAX_CONTEXT_CHARS = 18_000
_MAX_PAGE_BODY = 1_200
_MAX_CATEGORY_DESC = 400
_MAX_PRODUCT_DESC = 350
_MAX_ARTICLE_EXCERPT = 280
_MAX_PRODUCTS = 35
_MAX_ARTICLES = 12
_MAX_PAGES = 10

_PRIORITY_PAGE_SLUGS = (
    "kontakty",
    "faq",
    "company",
    "gde-kupit",
    "dokumentaciya",
    "zavod",
)


def _truncate(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def build_site_routes_block() -> str:
    """SEO-описания публичных разделов (для сборки KB-файла)."""
    lines: list[str] = []
    for path in sorted(PUBLIC_STATIC_ROUTES):
        meta = PUBLIC_STATIC_ROUTES[path]
        title = (meta.get("title") or "").strip()
        desc = (meta.get("description") or "").strip()
        if title or desc:
            lines.append(f"- {path}: {title}. {desc}".strip())
    return "\n".join(lines) if lines else "—"


def build_faq_items_block(*, limit: int = 30) -> str:
    """Активные FAQ из Admin (для сборки KB-файла)."""
    rows = FaqItem.objects.filter(is_active=True).order_by("order", "id").values("question", "answer")[:limit]
    lines: list[str] = []
    for row in rows:
        q = str(row["question"]).strip()
        a = str(row["answer"]).strip()
        if q and a:
            lines.append(f"В: {q}\nО: {a}")
    return "\n\n".join(lines) if lines else "—"


def build_pages_block() -> str:
    """Текст CMS-страниц (для сборки KB-файла)."""
    slugs = list(_PRIORITY_PAGE_SLUGS)
    extra = (
        publicly_visible(Page)
        .exclude(slug__in=slugs)
        .order_by("slug")
        .values_list("slug", flat=True)[: max(0, _MAX_PAGES - len(slugs))]
    )
    ordered_slugs = slugs + list(extra)
    lines: list[str] = []
    for slug in ordered_slugs[:_MAX_PAGES]:
        page = publicly_visible(Page).filter(slug=slug).first()
        if page is None:
            continue
        body = _truncate(strip_html_to_text(page.body), _MAX_PAGE_BODY)
        header = f"### /{page.slug} — {page.title.strip()}"
        if body:
            lines.append(f"{header}\n{body}")
        else:
            lines.append(header)
    return "\n\n".join(lines) if lines else "—"


def build_articles_block() -> str:
    """Анонсы статей (для сборки KB-файла)."""
    rows = (
        publicly_visible(Article)
        .order_by("-published_at", "-id")
        .values(
            "title",
            "slug",
            "excerpt",
            "body",
        )[:_MAX_ARTICLES]
    )
    lines: list[str] = []
    for row in rows:
        title = str(row["title"]).strip()
        slug = str(row["slug"]).strip()
        excerpt = str(row["excerpt"] or "").strip()
        if not excerpt:
            excerpt = _truncate(strip_html_to_text(str(row["body"] or "")), _MAX_ARTICLE_EXCERPT)
        else:
            excerpt = _truncate(excerpt, _MAX_ARTICLE_EXCERPT)
        if title and slug:
            lines.append(f"- /statyi/{slug} — {title}. {excerpt}".strip())
    return "\n".join(lines) if lines else "—"


def build_catalog_categories_block() -> str:
    """Категории каталога (для сборки KB-файла)."""
    from catalog.models import Category

    rows = Category.objects.order_by("name").values("name", "slug", "description", "instructions")
    lines: list[str] = []
    for row in rows:
        name = str(row["name"]).strip()
        slug = str(row["slug"]).strip()
        desc = _truncate(strip_html_to_text(str(row["description"] or "")), _MAX_CATEGORY_DESC)
        instr = _truncate(strip_html_to_text(str(row["instructions"] or "")), 200)
        chunk = f"- /catalog/{slug} — {name}"
        if desc:
            chunk += f". {desc}"
        if instr:
            chunk += f" Инструкция: {instr}"
        lines.append(chunk)
    return "\n".join(lines) if lines else "—"


def build_catalog_products_block(*, sku_tokens: tuple[str, ...] = ()) -> str:
    """Карточки каталога (для сборки KB-файла)."""
    from catalog.models import SKU, Product
    from catalog.urls_paths import catalog_path_for_sku

    base_qs = (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .order_by("product__category__name", "product__name", "sku_code")
    )
    skus = list(base_qs[:_MAX_PRODUCTS])
    if sku_tokens:
        matched = [
            sku
            for sku in base_qs
            if any(token in sku.sku_code.casefold().replace("-", "").replace("_", "") for token in sku_tokens)
        ]
        if matched:
            seen = {sku.pk for sku in matched}
            skus = matched[:8] + [sku for sku in skus if sku.pk not in seen][: max(0, 8 - len(matched))]
    lines: list[str] = []
    for sku in skus:
        product = cast(Product, sku.product)
        desc = _truncate(
            strip_html_to_text((product.description or "") + " " + (product.instructions or "")),
            _MAX_PRODUCT_DESC,
        )
        path = catalog_path_for_sku(sku)
        line = f"- {path} — {product.name.strip()} ({sku.sku_code})"
        if desc:
            line += f". {desc}"
        lines.append(line)
    return "\n".join(lines) if lines else "—"


def build_knowledge_context(
    *,
    max_chars: int = _MAX_CONTEXT_CHARS,
    user_query: str = "",
) -> str:
    """Select KB branches from ``gigachat_kb.txt`` only (no live DB at runtime)."""
    return search_kb_context(user_query, max_chars=max_chars)
