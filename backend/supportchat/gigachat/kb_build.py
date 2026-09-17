"""Build packaged GigaChat KB from local manuals + CMS snapshot."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from catalog.etl.manual_pdfs import default_manuals_dir
from supportchat.gigachat.kb_branches import (
    KB_FORMAT_VERSION,
    KbBranch,
    KbFileMeta,
    _build_voltage_sku_table,
    build_index_branch,
    build_policy_branch,
    format_bot_kb_document,
    series_from_manual_label,
    tokens_from_manual_content,
)
from supportchat.gigachat.kb_text import PACKAGED_KB_PATH, ManualChunk
from supportchat.gigachat.manuals_kb import (
    default_manuals_ru_dir,
    extract_manual_html_text,
    extract_manual_pdf_text,
)

_BUILD_HTML_CHARS = 4_000
_BUILD_PDF_PAGES = 8
_BUILD_PDF_CHARS = 4_000


def _slug_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "item"


def _slug_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _faq_search_tokens(question: str, answer: str) -> frozenset[str]:
    """FAQ tokens without bare numbers like 230 polluting voltage search."""
    words = re.findall(r"[a-zа-яё0-9]{3,}", f"{question} {answer}")
    tokens = {_slug_token(word) for word in words[:16]}
    return frozenset(token for token in tokens if token and not token.isdigit())


def _enrich_manual_body(text: str) -> str:
    table = _build_voltage_sku_table(text)
    if not table:
        return text
    return f"{table}\n\n{text}"


def iter_manual_chunks_for_build(
    *,
    manuals_ru_dir: Path | None = None,
    manuals_pdf_dir: Path | None = None,
) -> list[ManualChunk]:
    """Collect manual excerpts from local folders for packaging."""
    ru_dir = manuals_ru_dir or default_manuals_ru_dir()
    pdf_dir = manuals_pdf_dir or default_manuals_dir()
    chunks: list[ManualChunk] = []

    from supportchat.gigachat.manuals_kb import _html_title, _iter_html_manual_paths

    for path in _iter_html_manual_paths(ru_dir):
        text = extract_manual_html_text(path, max_chars=_BUILD_HTML_CHARS)
        if not text:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            raw = ""
        rel = path.relative_to(ru_dir)
        title = _html_title(raw, path.stem)
        chunks.append(
            ManualChunk(
                source="html",
                label=f"_manuals-ru/{rel} — {title}",
                text=text,
            ),
        )

    from catalog.etl.manual_pdfs import iter_manual_pdfs

    for path in iter_manual_pdfs(pdf_dir, "*.pdf"):
        text = extract_manual_pdf_text(
            path,
            max_pages=_BUILD_PDF_PAGES,
            max_chars=_BUILD_PDF_CHARS,
        )
        if not text:
            continue
        try:
            rel = path.relative_to(pdf_dir)
        except ValueError:
            rel = Path(path.name)
        chunks.append(
            ManualChunk(
                source="pdf",
                label=f"_инструкции-pdf/{rel}",
                text=text,
            ),
        )
    return chunks


def _manual_branch_id(chunk: ManualChunk) -> str:
    stem = Path(chunk.label.split("—")[0].split()[-1]).stem
    family = "pdf" if chunk.source == "pdf" else "html"
    return f"manual.{family}.{_slug_id(stem)}"


def _manual_branch_tags(chunk: ManualChunk) -> frozenset[str]:
    tags = {"manual", chunk.source, "овк", "привод"}
    if "/DA/" in chunk.label.upper() or chunk.label.upper().startswith("_MANUALS-RU/DA"):
        tags.add("da")
    if "/SA/" in chunk.label.upper():
        tags.add("sa")
    if "mu" in chunk.label.casefold():
        tags.add("mu")
        tags.add("момент")
    if "fu" in chunk.label.casefold():
        tags.add("fu")
        tags.add("пружина")
    return frozenset(tags)


def build_site_branches() -> list[KbBranch]:
    """CMS/catalog snapshot as searchable branches (build-time)."""
    from supportchat.gigachat.knowledge import (
        build_articles_block,
        build_catalog_categories_block,
        build_catalog_products_block,
        build_pages_block,
        build_site_routes_block,
    )
    from supportchat.models import FaqItem

    branches: list[KbBranch] = []

    routes = build_site_routes_block()
    if routes != "—":
        branches.append(
            KbBranch(
                id="site.routes",
                title="Разделы сайта hoocon.ru",
                tags=frozenset({"site", "routes", "каталог", "контакты", "faq"}),
                body=routes,
            ),
        )

    for row in FaqItem.objects.filter(is_active=True).order_by("order", "id"):
        q = str(row.question).strip()
        a = str(row.answer).strip()
        if not q or not a:
            continue
        tags = frozenset({"faq", "admin", "чат"})
        branch_id = f"faq.admin.{row.pk}"
        if row.show_on_home:
            tags = frozenset({"faq", "home", "овк", "admin"})
            branch_id = f"faq.home.{row.pk}"
        branches.append(
            KbBranch(
                id=branch_id,
                title=f"FAQ: {q[:80]}",
                tags=tags,
                tokens=_faq_search_tokens(q, a),
                body=f"В: {q}\nО: {a}",
            ),
        )

    pages = build_pages_block()
    if pages != "—":
        branches.append(
            KbBranch(
                id="site.pages",
                title="Страницы сайта (CMS)",
                tags=frozenset({"site", "pages", "контакты", "компания"}),
                body=pages,
            ),
        )

    articles = build_articles_block()
    if articles != "—":
        branches.append(
            KbBranch(
                id="site.articles",
                title="Статьи /statyi",
                tags=frozenset({"site", "articles", "статьи"}),
                body=articles,
            ),
        )

    categories = build_catalog_categories_block()
    if categories != "—":
        branches.append(
            KbBranch(
                id="site.catalog.categories",
                title="Категории каталога",
                tags=frozenset({"catalog", "категории", "серии"}),
                body=categories,
            ),
        )

    products = build_catalog_products_block()
    if products != "—":
        branches.append(
            KbBranch(
                id="site.catalog.products",
                title="Линейки каталога (SKU)",
                tags=frozenset({"catalog", "sku", "привод", "кран"}),
                body=products,
            ),
        )

    return branches


def build_kb_branches(
    *,
    manuals_ru_dir: Path | None = None,
    manuals_pdf_dir: Path | None = None,
    include_site: bool = True,
) -> list[KbBranch]:
    """Assemble all branches for the bot KB file."""
    branches: list[KbBranch] = [build_policy_branch()]
    if include_site:
        branches.extend(build_site_branches())

    for chunk in iter_manual_chunks_for_build(
        manuals_ru_dir=manuals_ru_dir,
        manuals_pdf_dir=manuals_pdf_dir,
    ):
        body = _enrich_manual_body(chunk.text)
        branches.append(
            KbBranch(
                id=_manual_branch_id(chunk),
                title=chunk.label,
                tags=_manual_branch_tags(chunk),
                series=series_from_manual_label(chunk.label),
                tokens=tokens_from_manual_content(chunk.label, body),
                body=body,
            ),
        )

    branches.append(build_index_branch(branches))
    return branches


def write_packaged_kb(
    output: Path | None = None,
    *,
    manuals_ru_dir: Path | None = None,
    manuals_pdf_dir: Path | None = None,
    include_site: bool = True,
) -> Path:
    """Write unified ``gigachat_kb.txt`` with @BRANCH markers."""
    branches = build_kb_branches(
        manuals_ru_dir=manuals_ru_dir,
        manuals_pdf_dir=manuals_pdf_dir,
        include_site=include_site,
    )
    manual_count = sum(1 for branch in branches if branch.id.startswith("manual."))
    if manual_count == 0:
        raise RuntimeError(
            "Нет данных для сборки: проверьте _manuals-ru и _инструкции-pdf в корне репозитория.",
        )

    meta = KbFileMeta(
        version=KB_FORMAT_VERSION,
        built_at=datetime.now(UTC).isoformat(),
        branch_count=len(branches),
    )
    document = format_bot_kb_document(branches, meta=meta)

    out = (output or PACKAGED_KB_PATH).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    return out
