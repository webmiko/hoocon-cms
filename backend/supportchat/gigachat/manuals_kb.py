"""Manual text extraction and selection for the unified GigaChat KB file."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from catalog.etl.html_text import html_to_structured_text
from supportchat.gigachat.kb_text import ManualChunk

logger = logging.getLogger("hoocon.supportchat.gigachat")

_HTML_FAMILY_DIRS: tuple[str, ...] = ("DA", "SA", "HV", "H81")
_HTML_SKIP_NAMES: frozenset[str] = frozenset({"index.html", "constructor.html"})
_HTML_SKIP_PREFIXES: tuple[str, ...] = ("template", "constructor")
_RUNTIME_PDF_PAGES = 3
_RUNTIME_PDF_CHARS = 450
_NOISE_LINE_RE = re.compile(
    r"^(?:\d{1,2}|123456789101112|Колонки|Печать / PDF|все инструкции|hoocon\.ru)$",
    re.I,
)
_SKU_TOKEN_RE = re.compile(
    r"(?i)(?:da|sa|hv[ad]|8100)(?:\d+mu|\d+fu|\d+mqu|[a-z0-9][a-z0-9\-_/]{1,})",
)
_SKU_NORMALIZE_RE = re.compile(r"(?i)\b(da|sa|hv)\s*(\d+)\s*(mu|fu|mqu)\b")
_SPEC_MARKERS: tuple[str, ...] = (
    "технические характеристики",
    "крутящий момент",
    "номинальное напряжение",
    "время поворота",
    "потребляемая мощность",
)
_FOOTER_MARKERS: tuple[str, ...] = (
    "юридический адрес",
    "многоканальный телефон",
    "www.hoocon.ru",
    "отдел продаж",
)


def normalize_product_query(query: str) -> str:
    """Collapse spaces inside DA2 MU / DA 4MU style tokens."""
    return _SKU_NORMALIZE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{match.group(3)}",
        query,
    )


def extract_voltage_hint(query: str) -> str | None:
    """24 or 230 when the client specified supply voltage."""
    compact = re.sub(r"\s+", "", (query or "").casefold().replace("в", "v"))
    if re.search(r"(?:^|[^\d])24v(?:[^\d]|$)|ac/dc24|на24", compact):
        return "24"
    if re.search(r"230v|на230|100.?240", compact):
        return "230"
    return None


def extract_sku_tokens(query: str) -> tuple[str, ...]:
    """Series / SKU tokens from the latest user message."""
    normalized = normalize_product_query(query or "")
    found = _SKU_TOKEN_RE.findall(normalized)
    tokens: list[str] = []
    for token in found:
        tokens.append(token.casefold().replace("_", "-"))
    volt = extract_voltage_hint(query)
    if volt:
        for token in list(tokens):
            if re.search(r"(mu|fu|mqu)$", token):
                tokens.append(f"{token}{volt}")
    return tuple(dict.fromkeys(tokens))


def _prioritize_manual_specs(text: str) -> str:
    """Put torque/spec lines first so excerpts survive char limits."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    priority: list[str] = []
    footer: list[str] = []
    body: list[str] = []
    for line in lines:
        low = line.casefold()
        if any(marker in low for marker in _FOOTER_MARKERS):
            footer.append(line)
        elif any(marker in low for marker in _SPEC_MARKERS):
            priority.append(line)
        else:
            body.append(line)
    if not priority:
        return text
    ordered = priority + body + footer
    return "\n".join(ordered)


def default_manuals_ru_dir(repo_root: Path | None = None) -> Path:
    """Resolve ``_manuals-ru`` next to the Django project root (build only)."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[3]
    return (repo_root / "_manuals-ru").resolve()


def _strip_html_shell(raw: str) -> str:
    """Drop CSS/JS and keep manual body markup."""
    text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    stage = re.search(r'<div class="stage">(.*?)</div>\s*<script', text, flags=re.I | re.S)
    if stage:
        return stage.group(1)
    body = re.search(r"<body[^>]*>(.*)</body>", text, flags=re.I | re.S)
    if body:
        return body.group(1)
    return text


def _clean_manual_text(text: str, *, max_chars: int) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        row = line.strip()
        if not row or _NOISE_LINE_RE.match(row):
            continue
        lines.append(row)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _html_title(raw: str, fallback: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or fallback


def extract_manual_html_text(path: Path, *, max_chars: int) -> str:
    """Plain text from a RU manual HTML under ``_manuals-ru``."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("manual_html_read_failed path=%s", path)
        return ""
    body = _strip_html_shell(raw)
    structured = html_to_structured_text(body)
    prioritized = _prioritize_manual_specs(structured)
    return _clean_manual_text(prioritized, max_chars=max_chars)


def extract_manual_pdf_text(
    path: Path,
    *,
    max_pages: int = _RUNTIME_PDF_PAGES,
    max_chars: int = _RUNTIME_PDF_CHARS,
) -> str:
    """Plain text from the first pages of a RU instruction PDF."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2_missing pdf=%s", path.name)
        return ""
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception:
        logger.warning("manual_pdf_open_failed path=%s", path)
        return ""
    parts: list[str] = []
    try:
        page_count = len(document)
        for index in range(min(page_count, max_pages)):
            page = document[index]
            text_page = page.get_textpage()
            count = text_page.count_chars()
            if count <= 0:
                continue
            parts.append(text_page.get_text_range(0, count))
    finally:
        document.close()
    prioritized = _prioritize_manual_specs("\n".join(parts))
    return _clean_manual_text(prioritized, max_chars=max_chars)


def _iter_html_manual_paths(manuals_ru_dir: Path) -> list[Path]:
    if not manuals_ru_dir.is_dir():
        return []
    paths: list[Path] = []
    for family in _HTML_FAMILY_DIRS:
        family_dir = manuals_ru_dir / family
        if not family_dir.is_dir():
            continue
        for path in sorted(family_dir.glob("*.html")):
            name = path.name.casefold()
            if name in _HTML_SKIP_NAMES:
                continue
            if any(name.startswith(prefix) for prefix in _HTML_SKIP_PREFIXES):
                continue
            paths.append(path)
    return paths


def _token_matches_label(token: str, label: str) -> bool:
    """Avoid DA2MU matching unrelated DA20… manuals."""
    if token in label:
        return True
    stem = re.sub(r"\d+$", "", token)
    if stem.endswith("mu") and stem in label:
        return True
    return False


def _score_chunk(chunk: ManualChunk, query: str) -> int:
    """Relevance of a manual chunk to the latest user message."""
    q = (query or "").casefold().strip()
    if not q:
        return 0
    label = chunk.label.casefold()
    text = chunk.text.casefold()
    score = 0
    for token in extract_sku_tokens(query):
        if _token_matches_label(token, label):
            score += 50
        elif token in text:
            score += 35
        elif token.rstrip("0123456789") != token and token[:-1] in label:
            score -= 10
    for word in re.findall(r"[a-zа-яё0-9]{3,}", q):
        if word in {"момент", "привод", "заслонк", "вентил"}:
            continue
        if word in label:
            score += 4
        if word in text:
            score += 1
    return score


def select_manual_chunks(
    chunks: tuple[ManualChunk, ...],
    *,
    query: str,
    max_chars: int,
) -> list[ManualChunk]:
    """Pick manual excerpts for the prompt (relevant first, then fill budget)."""
    if not chunks:
        return []
    ranked = sorted(
        chunks,
        key=lambda c: (-_score_chunk(c, query), c.label),
    )
    if not (query or "").strip():
        ranked = list(chunks)

    selected: list[ManualChunk] = []
    used = 0
    for chunk in ranked:
        block_len = len(chunk.label) + len(chunk.text) + 8
        if used + block_len > max_chars:
            if used == 0 and max_chars > 200:
                trimmed = chunk.text[: max_chars - len(chunk.label) - 12] + "…"
                selected.append(ManualChunk(chunk.source, chunk.label, trimmed))
            break
        selected.append(chunk)
        used += block_len
    return selected


def build_manuals_knowledge_block(
    max_chars: int = 9_000,
    *,
    user_query: str = "",
) -> str:
    """Legacy alias — runtime uses branch search in ``search_kb_context``."""
    from supportchat.gigachat.kb_branches import search_kb_context

    return search_kb_context(user_query, max_chars=max_chars)
