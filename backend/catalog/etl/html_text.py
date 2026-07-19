"""HTML → plain text for catalog descriptions (Tilda markup)."""

from __future__ import annotations

import html
import json
import re

_TAG = re.compile(r"<[^>]+>")
_BLOCK_BREAK = re.compile(
    r"(?i)</(p|div|li|h[1-6]|tr|br)\s*>|<br\s*/?>",
)
_MULTI_NL = re.compile(r"\n{3,}")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SCRIPT_STYLE = re.compile(
    r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
)
_LIST_ITEM = re.compile(r"(?is)<li[^>]*>(.*?)</li>")
_HEADING_STRONG = re.compile(r"(?is)<(?:strong|b|h[1-6])[^>]*>(.*?)</(?:strong|b|h[1-6])>")
_FIELD_TEXT = re.compile(
    r"""field=["']text["'][^>]*>(.*?)</div>""",
    re.I | re.S,
)
_JSON_DESCR = re.compile(
    r'''"descr"\s*:\s*"((?:\\.|[^"\\])*)"''',
)
_JSON_TEXT = re.compile(
    r'''"text"\s*:\s*"((?:\\.|[^"\\])*)"''',
)

# Noise from scraping raw HTML attributes / chrome.
_NOISE = re.compile(
    r"""(?ix)
    (?:
        ^["'/>\s]+
        | ["']\s*/?>
        | \b(?:class|style|label|field|id|href|src|data-[\w-]+)\s*=
        | \b(?:js-|tn-|t-|uc-|btnflex|menu-item|nav-|cookie)
        | \b(?:Позвонить|Написать|Главная|Меню навигации)
        | \b(?:Делаем управление простым)
        | [{};]|^\s*[#.][\w-]+
    )
    """,
)
_BULLET_PREFIX = re.compile(r"^[\s–—\-•·*]+")
_SPEC_HINT = re.compile(
    r"(?i)(?:Нм|м²|IP\d{2}|DN\s*\d|В\b|сек|дБ|МПа|°|градус|"
    r"момент|напряжен|площад|управл|угол|защит|мощност|провод|"
    r"давлени|температур|уплотнен|ходов)",
)
_SPEC_PRIORITY = re.compile(
    r"(?i)(?:"
    r"Общие характеристики|Электрические параметры|"
    r"Крутящий момент|Технические характеристики|"
    r"Рабочее давление"
    r")",
)
_INSTALL_HINT = re.compile(
    r"(?i)(?:Подготовка к установке|Монтаж привода|ключевые этапы|"
    r"Инструменты|Рекомендац)",
)


def html_to_text(raw: str) -> str:
    """Convert Tilda HTML description to readable plain text.

    Args:
        raw: HTML or plain string from Tilda `descr` / `text` / tabs.

    Returns:
        Cleaned plain text (may be empty).
    """
    if not raw or not str(raw).strip():
        return ""
    text = str(raw)
    text = _BLOCK_BREAK.sub("\n", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def html_to_structured_text(raw: str) -> str:
    """Convert product HTML into lead paragraphs + bullet lines.

    Preserves list items as ``– …`` lines and section titles ending with ``:``.

    Args:
        raw: HTML fragment (Tilda ``field="text"``) or plain text.

    Returns:
        Structured plain text suitable for PDP rendering.
    """
    if not raw or not str(raw).strip():
        return ""

    fragment = str(raw)
    fragment = _SCRIPT_STYLE.sub(" ", fragment)

    # Normalize list items before stripping tags.
    def _li_repl(match: re.Match[str]) -> str:
        inner = html_to_text(match.group(1))
        if not inner:
            return "\n"
        return f"\n– {inner}\n"

    fragment = _LIST_ITEM.sub(_li_repl, fragment)

    # Section titles from strong/b/h*
    def _head_repl(match: re.Match[str]) -> str:
        title = html_to_text(match.group(1)).strip(" :")
        if not title:
            return "\n"
        if len(title) <= 60 and not title.startswith("–"):
            return f"\n\n{title}:\n"
        return f"\n{title}\n"

    fragment = _HEADING_STRONG.sub(_head_repl, fragment)
    fragment = _BLOCK_BREAK.sub("\n", fragment)
    fragment = _TAG.sub("", fragment)
    fragment = html.unescape(fragment)
    fragment = fragment.replace("\xa0", " ")
    fragment = _MULTI_SPACE.sub(" ", fragment)

    lines: list[str] = []
    for raw_line in fragment.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        # Short "Label:" lines become section titles (nested Tilda lists).
        bare = _BULLET_PREFIX.sub("", line).strip()
        if bare.endswith(":") and 3 <= len(bare) <= 50:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(bare)
            continue
        line = _BULLET_PREFIX.sub("– ", line, count=1) if _is_bulletish(line) else line
        line = line.strip()
        if is_noise_line(line):
            continue
        if lines and lines[-1] == line:
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = _squeeze_bullet_gaps(text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def _squeeze_bullet_gaps(text: str) -> str:
    """Remove blank lines that split a contiguous bullet list."""
    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        if line == "" and out and out[-1].startswith("– "):
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if nxt.startswith("– "):
                continue
        out.append(line)
    return "\n".join(out)


def _is_bulletish(line: str) -> bool:
    """Return True if line should be normalized to a bullet."""
    stripped = line.lstrip()
    if stripped.startswith(("–", "—", "-", "•", "·", "*")):
        return True
    return False


def is_noise_line(line: str) -> bool:
    """Filter chrome / leftover markup from scraped lines.

    Args:
        line: Candidate description line.

    Returns:
        True if the line should be discarded.
    """
    if not line or len(line) < 3:
        return True
    # Long prose lines are valid product copy; only reject extreme blobs.
    if len(line) > 1200:
        return True
    if _NOISE.search(line):
        return True
    if any(ch in line for ch in ("<", ">", "{", "}")):
        return True
    if line.count("=") >= 2:
        return True
    return False


def _unescape_json_string(raw: str) -> str:
    """Decode a JSON string literal body (handles \\uXXXX and \\/)."""
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        text = raw.replace(r"\/", "/").replace(r"\n", "\n").replace(r"\"", '"')
        return html.unescape(text)


def extract_embedded_store_html(page_html: str) -> list[str]:
    """Extract Tilda store ``descr`` / ``text`` HTML from embedded JSON.

    Args:
        page_html: Full product page HTML.

    Returns:
        HTML fragments from store product payload.
    """
    blocks: list[str] = []
    for pattern in (_JSON_DESCR, _JSON_TEXT):
        for match in pattern.finditer(page_html):
            fragment = _unescape_json_string(match.group(1)).strip()
            if len(fragment) < 40:
                continue
            plain = html_to_text(fragment)
            if not _SPEC_HINT.search(plain):
                continue
            blocks.append(fragment)
    blocks.sort(key=len, reverse=True)
    return blocks


def extract_product_text_blocks(page_html: str) -> list[str]:
    """Pull product copy from Tilda text fields and store JSON.

    Specs blocks (Общие характеристики / Крутящий момент) rank above
    long installation guides.

    Args:
        page_html: Full product page HTML.

    Returns:
        List of HTML fragments (most relevant first).
    """
    scored: list[tuple[int, int, str]] = []

    def _consider(body: str) -> None:
        plain = html_to_text(body)
        if len(plain) < 40:
            return
        if not _SPEC_HINT.search(plain):
            return
        if is_noise_line(plain[:80]):
            return
        # Skip legal/footer chrome
        if re.search(r"(?i)договор оферты|cookie-файл|публичной офертой", plain):
            return
        score = 0
        if _SPEC_PRIORITY.search(plain):
            score += 100
        if _INSTALL_HINT.search(plain):
            score -= 40
        if 200 <= len(plain) <= 2500:
            score += 20
        elif len(plain) > 4000:
            score -= 30
        scored.append((score, len(plain), body))

    for match in _FIELD_TEXT.finditer(page_html):
        _consider(match.group(1))
    for body in extract_embedded_store_html(page_html):
        _consider(body)

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    # Deduplicate by plain text prefix
    out: list[str] = []
    seen: set[str] = set()
    for _, _, body in scored:
        key = html_to_text(body)[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(body)
    return out


def compose_product_description(
    *,
    meta_description: str = "",
    html_blocks: list[str] | None = None,
    extra_bullets: list[str] | None = None,
) -> str:
    """Build a clean structured description for Product/SKU.

    Args:
        meta_description: og/meta description (lead paragraph).
        html_blocks: Tilda text field HTML fragments (already ranked).
        extra_bullets: Optional already-clean bullet lines.

    Returns:
        Structured plain text.
    """
    parts: list[str] = []
    lead = html_to_text(meta_description).strip()
    if lead and not is_noise_line(lead):
        parts.append(lead)

    # Specs first, then at most one install/FAQ block
    used_install = False
    for block in html_blocks or []:
        plain = html_to_text(block)
        is_install = bool(_INSTALL_HINT.search(plain)) and not _SPEC_PRIORITY.search(
            plain,
        )
        if is_install:
            if used_install:
                continue
            used_install = True
        structured = html_to_structured_text(block)
        if not structured:
            continue
        if lead and structured.startswith(lead[:40]):
            structured = structured[len(lead) :].lstrip("\n")
        if structured:
            parts.append(structured)

    bullets = [b for b in (extra_bullets or []) if b and not is_noise_line(b)]
    if bullets and not any("– " in p for p in parts):
        parts.append("\n".join(f"– {b.lstrip('–—- ')}" for b in bullets))

    text = "\n\n".join(p for p in parts if p).strip()
    return dedupe_description_lines(_MULTI_NL.sub("\n\n", text))


def dedupe_description_lines(raw: str) -> str:
    """Drop repeated lines in a structured description (keep first occurrence).

    Compares lines case-insensitively after normalizing whitespace and bullet
    prefixes, so ``– Foo`` and ``Foo`` count as the same.

    Args:
        raw: Structured plain text.

    Returns:
        Deduplicated text.
    """
    if not raw or not raw.strip():
        return ""
    seen: set[str] = set()
    out: list[str] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        key = _description_line_key(line)
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return _MULTI_NL.sub("\n\n", "\n".join(out)).strip()


def _description_line_key(line: str) -> str:
    """Normalize a description line for duplicate detection."""
    text = " ".join(line.casefold().split())
    text = _BULLET_PREFIX.sub("", text).strip()
    text = text.rstrip(":")
    return text


def clean_polluted_description(raw: str) -> str:
    """Remove leftover markup noise from an already-stored description.

    Args:
        raw: Stored Product/SKU description.

    Returns:
        Cleaned structured text (may be empty if everything was noise).
    """
    if not raw:
        return ""
    # If HTML tags still present — convert first
    text = html_to_structured_text(raw) if "<" in raw else raw
    text = text.replace("\xa0", " ")
    kept: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        if is_noise_line(line):
            continue
        # Strip trailing attribute junk like …РФ!">
        line = re.sub(r"""["']\s*/?>?\s*$""", "", line).rstrip()
        if not line or is_noise_line(line):
            continue
        if kept and kept[-1] == line:
            continue
        kept.append(line)
    return dedupe_description_lines("\n".join(kept))


# ── Tilda product tabs (Описание / Инструкция / Характеристики / Аналоги) ──

_TAB_OPTION = re.compile(
    r'<option value="(?P<id>\d+)">'
    r"(?P<title>Описание|Инструкция|Характеристики|Аналоги)</option>",
    re.I,
)
_REC_BLOCK = re.compile(
    r'<div id="rec(?P<id>\d+)"(?P<body>.*?)(?=<div id="rec\d+"|$)',
    re.I | re.S,
)
_TAB_KEY = {
    "описание": "description",
    "инструкция": "instructions",
    "характеристики": "specs",
    "аналоги": "analogs",
}


def extract_tilda_tabs(page_html: str) -> dict[str, str]:
    """Extract structured text for the four Tilda product tabs.

    Tabs are wired via ``<option value="{rec_id}">Описание</option>`` to
    ``<div id="rec{rec_id}">`` blocks (see hoocon.ru product pages).

    Args:
        page_html: Full product page HTML.

    Returns:
        Mapping with keys ``description``, ``instructions``, ``specs``,
        ``analogs`` (missing tabs omitted; values are plain structured text).
    """
    if not page_html:
        return {}
    id_to_key: dict[str, str] = {}
    for match in _TAB_OPTION.finditer(page_html):
        title = match.group("title").casefold()
        key = _TAB_KEY.get(title)
        if key:
            id_to_key[match.group("id")] = key

    if not id_to_key:
        return {}

    out: dict[str, str] = {}
    for match in _REC_BLOCK.finditer(page_html):
        key = id_to_key.get(match.group("id"))
        if not key:
            continue
        chunk = match.group("body")
        # Whole record → structured text (nested </div> breaks field=text regex).
        text = html_to_structured_text(chunk)
        text = dedupe_description_lines(text)
        if text and len(html_to_text(text)) >= 20:
            out[key] = text
    return out


def filter_analogs_for_sku(text: str, sku_code: str) -> str:
    """Keep analog blocks that mention this SKU edition.

    Tilda pages list analogs per edition (``DA3FU230-DS``, ``DA3FU24-DS``).
    When no edition marker matches, return the full text unchanged.

    Args:
        text: Full «Аналоги» tab text.
        sku_code: Edition code, e.g. ``da3fu230-ds``.

    Returns:
        Filtered plain text.
    """
    if not text or not text.strip():
        return ""
    code = (sku_code or "").strip()
    if not code:
        return text.strip()

    # Match by series+voltage core so ``da3fu230-d`` picks ``DA3FU230-DS`` blocks.
    raw = code.casefold()
    core = re.sub(r"-(?:ds|as|dst|d|a|t)$", "", raw)
    needle = re.sub(r"[\s_\-]+", "", core or raw)
    if not needle:
        return text.strip()

    lines = text.replace("\xa0", " ").splitlines()
    blocks: list[list[str]] = [[]]
    header_re = re.compile(
        r"(?i)^(основные характеристики|аналоги привода|важные параметры)\b"
        r"|^[A-Z]{2,}\d+[A-Z]*\d*(?:-|\s|$)",
    )
    for line in lines:
        stripped = line.strip()
        starts = bool(header_re.search(stripped))
        if starts and blocks[-1] and any(x.strip() for x in blocks[-1]):
            blocks.append([])
        blocks[-1].append(line)

    matched: list[str] = []
    for block in blocks:
        blob = re.sub(r"[\s_\-]+", "", "\n".join(block).casefold())
        if needle in blob:
            matched.extend(block)
            matched.append("")

    if matched:
        return dedupe_description_lines("\n".join(matched).strip())
    return text.strip()
