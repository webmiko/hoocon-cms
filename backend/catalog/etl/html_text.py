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
# Newer Tilda t819 tabs: button aria-controls → content-tabN_recId panel.
_TAB_BUTTON = re.compile(
    r'<button[^>]*\baria-controls="(?P<panel>content-tab\d+_\d+)"[^>]*>\s*'
    r"(?P<title>Описание|Инструкция|Характеристики|Аналоги)\s*</button>",
    re.I,
)
_CONTENT_TAB_PANEL = re.compile(
    r'<div[^>]*\bid="(?P<id>content-tab\d+_\d+)"[^>]*>(?P<body>.*?)'
    r'(?=<div[^>]*\bid="content-tab\d+_|\Z)',
    re.I | re.S,
)
_SAFETY_NOTICE = re.compile(
    r"(?is)Оповещение\s+по\s+безопасности\s*(?:</(?:strong|b|span|p|div)>\s*)?"
    r"(?P<body>(?:(?:<br\s*/?>|\s)*\d+\.\s*.+?){2,4})"
    r"(?=<|$)",
)
_TAB_KEY = {
    "описание": "description",
    "инструкция": "instructions",
    "характеристики": "specs",
    "аналоги": "analogs",
}


def _plain_tab_text(chunk: str) -> str:
    """Structured plain text for one tab body, or empty if too short."""
    text = html_to_structured_text(chunk)
    text = dedupe_description_lines(text)
    if text and len(html_to_text(text)) >= 20:
        return text
    return ""


def extract_tilda_tabs(page_html: str) -> dict[str, str]:
    """Extract structured text for the four Tilda product tabs.

    Supports:

    - Legacy: ``<option value="{rec_id}">Описание</option>`` → ``#rec{id}``
    - t819: ``aria-controls="content-tabN_…"`` → ``#content-tabN_…`` panels

    Args:
        page_html: Full product page HTML.

    Returns:
        Mapping with keys ``description``, ``instructions``, ``specs``,
        ``analogs`` (missing tabs omitted; values are plain structured text).
    """
    if not page_html:
        return {}

    out = _extract_tilda_tabs_rec(page_html)
    if len(out) >= 2:
        return out
    t819 = _extract_tilda_tabs_t819(page_html)
    # Prefer the richer parse when both partially match.
    if len(t819) > len(out):
        return t819
    return out or t819


def _extract_tilda_tabs_rec(page_html: str) -> dict[str, str]:
    """Legacy rec-id tab wiring."""
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
        text = _plain_tab_text(match.group("body"))
        if text:
            out[key] = text
    return out


def _extract_tilda_tabs_t819(page_html: str) -> dict[str, str]:
    """t819 content-tab panels wired via aria-controls."""
    panel_to_key: dict[str, str] = {}
    for match in _TAB_BUTTON.finditer(page_html):
        title = match.group("title").casefold()
        key = _TAB_KEY.get(title)
        if key:
            panel_to_key[match.group("panel")] = key
    if not panel_to_key:
        return {}
    out: dict[str, str] = {}
    for match in _CONTENT_TAB_PANEL.finditer(page_html):
        key = panel_to_key.get(match.group("id"))
        if not key:
            continue
        text = _plain_tab_text(match.group("body"))
        if text:
            out[key] = text
    return out


def extract_safety_notice(page_html: str) -> str:
    """Extract the live «Оповещение по безопасности» block as structured text.

    Args:
        page_html: Full product page HTML.

    Returns:
        Plain text starting with ``ВНИМАНИЕ:`` (empty if not found).
    """
    if not page_html:
        return ""
    match = _SAFETY_NOTICE.search(page_html)
    if match is None:
        return ""
    body = html_to_text(match.group("body"))
    lines: list[str] = ["ВНИМАНИЕ:"]
    for part in re.split(r"(?=\d+\.\s)", body):
        item = " ".join(part.split()).strip()
        if not item:
            continue
        item = re.sub(r"^\d+\.\s*", "", item).strip()
        if item:
            lines.append(f"– {item}")
    if len(lines) < 2:
        return ""
    return "\n".join(lines)


def ensure_safety_in_instructions(instructions: str, safety: str) -> str:
    """Prepend a safety notice when instructions lack an Attention block.

    Args:
        instructions: Install / operation tab text.
        safety: ``ВНИМАНИЕ:`` block from the page or glossary.

    Returns:
        Instructions with safety near the top when needed.
    """
    body = (instructions or "").strip()
    notice = (safety or "").strip()
    if not notice:
        return body
    if re.search(
        r"(?im)(?:^|\n)\s*ВНИМАНИЕ\b|Оповещение\s+по\s+безопасности",
        body,
    ):
        return body
    if not body:
        return notice
    # Keep lead title line, then safety, then the rest.
    lines = body.splitlines()
    if lines and re.search(r"(?i)^инструкция\b", lines[0]):
        lead = lines[0]
        rest = "\n".join(lines[1:]).lstrip()
        return f"{lead}\n\n{notice}\n\n{rest}".strip()
    return f"{notice}\n\n{body}".strip()


def _analogs_edition_needles(sku_code: str) -> tuple[str, ...]:
    """Compact edition tokens for matching analog headers.

    Keeps voltage + control letter so ``DA4MU24-A`` does not pick ``…24-D/DS``
    blocks. ``-DS`` / ``-AS`` also match slash headers like ``DA4MU24-D/DS``.
    """
    raw = (sku_code or "").strip().casefold()
    if not raw:
        return ()
    compact = re.sub(r"[\s_\-]+", "", raw)
    needles = [compact]
    # Header ``DA4MU24-D/DS`` → blob ``da4mu24dds``; SKU ``…-DS`` → ``da4mu24ds``.
    if compact.endswith("dst"):
        needles.append(compact[:-3] + "ds")
        needles.append(compact[:-3] + "d")
    elif compact.endswith("ds"):
        needles.append(compact[:-1])  # …d
    elif compact.endswith("as"):
        needles.append(compact[:-1])  # …a
    elif compact.endswith("t") and len(compact) > 1:
        needles.append(compact[:-1])
    # Unique, longest first so ``da4mu24ds`` is tried before ``da4mu24d``.
    return tuple(sorted(dict.fromkeys(needles), key=len, reverse=True))


_ANALOGS_FULL_CODE_RE = re.compile(
    r"(?i)\b([a-z]{2,}\d+[a-z]*\d*-[a-z]{1,3})\b",
)
_ANALOGS_EDITION_HEADER_RE = re.compile(
    r"(?i)^(?P<prefix>для\s+(?:hoocon\s+)?|аналоги\s+для\s+)"
    r"(?P<body>.+?)"
    r"(?P<tail>\s*\([^)]*\))?\s*:?\s*$",
)
# SAMU: «Аналоги 24В (SA10MU24-DS/DST):» / «Аналоги 230В (SA10MU230-DS/DST)»
_ANALOGS_VOLTAGE_HEADER_RE = re.compile(
    r"(?i)^аналоги\s+(?P<volt>24|230)\s*в\s*"
    r"(?:\((?P<body>[^)]*)\))?\s*:?\s*$",
)
_ANALOGS_SHORT_SLASH_RE = re.compile(
    r"(?i)(?P<stem>[a-z]{2,}\d+[a-z]*\d*)-(?P<a>[ads]{1,3})\s*/\s*(?P<b>[ads]{1,3})\b",
)
_ANALOGS_MULTI_VOLT_OVERVIEW_RE = re.compile(
    r"(?i)^аналоги\s+.+\s+и\s+[a-z]{2,}\d",
)


def _compact_sku_token(code: str) -> str:
    """Lowercase SKU token without spaces / underscores / hyphens."""
    return re.sub(r"[\s_\-]+", "", (code or "").casefold())


def _control_suffix_family(suffix: str) -> str:
    """Map edition suffix to control family for slash-header matching."""
    suf = (suffix or "").casefold()
    if suf in {"a", "as"}:
        return "modulating"
    if suf in {"d", "ds", "dst"}:
        return "on_off"
    if suf == "m":
        return "modbus"
    return suf


def _sku_control_suffix(compact: str) -> str:
    """Trailing control letters from a compacted article (``da2mu230ds`` → ``ds``)."""
    for suf in ("dst", "ds", "as", "st", "a", "d", "m", "t", "s"):
        if compact.endswith(suf) and len(compact) > len(suf):
            return suf
    return ""


def _sku_voltage_token(sku_code: str) -> str | None:
    """Return ``24`` / ``230`` encoded in the article, if present."""
    match = re.search(r"(?i)(?:mu|fu|qu|hvd|hva)?(230|24)(?:-|$)", sku_code or "")
    if match:
        return match.group(1)
    match = re.search(r"(230|24)", sku_code or "")
    return match.group(1) if match else None


def _listed_editions_in_header(header: str) -> list[str]:
    """Full SKU codes listed in an analogs heading (slash groups)."""
    return [m.group(1) for m in _ANALOGS_FULL_CODE_RE.finditer(header)]


def _header_voltage_token(header: str) -> str | None:
    """Return ``24`` / ``230`` from an analogs heading, if present."""
    match = re.search(r"(?i)\b(230|24)\s*в\b", header or "")
    if match:
        return match.group(1)
    codes = _listed_editions_in_header(header)
    volts = {_sku_voltage_token(c) for c in codes}
    volts.discard(None)
    if len(volts) == 1:
        return next(iter(volts))  # type: ignore[arg-type]
    return None


def _sku_matches_analogs_header(sku_code: str, header: str) -> bool | None:
    """Whether ``sku_code`` belongs to this edition heading.

    Returns:
        True / False when the heading lists concrete editions or a voltage
        band; None when the line is not an edition list (fall back to blob
        needles).
    """
    volt_header = _ANALOGS_VOLTAGE_HEADER_RE.match(header.strip())
    listed = _listed_editions_in_header(header)
    short = _ANALOGS_SHORT_SLASH_RE.search(header.replace(" ", ""))
    header_volt = _header_voltage_token(header)
    sku_volt = _sku_voltage_token(sku_code)

    if volt_header is not None:
        band = volt_header.group("volt")
        if sku_volt and sku_volt != band:
            return False
        body = volt_header.group("body") or ""
        if body.strip():
            return _sku_matches_listed_or_slash(sku_code, body) is not False
        return True

    if not listed and short is None:
        return None

    if header_volt and sku_volt and header_volt != sku_volt:
        return False

    return _sku_matches_listed_or_slash(sku_code, header)


def _sku_matches_listed_or_slash(sku_code: str, header: str) -> bool | None:
    """Match SKU against full codes and ``STEM-D/DS`` slash groups in ``header``."""
    listed = _listed_editions_in_header(header)
    short = _ANALOGS_SHORT_SLASH_RE.search(header.replace(" ", ""))
    if not listed and short is None:
        return None

    sku_compact = _compact_sku_token(sku_code)
    sku_suf = _sku_control_suffix(sku_compact)
    sku_fam = _control_suffix_family(sku_suf)
    sku_stem = sku_compact[: -len(sku_suf)] if sku_suf else sku_compact

    if listed:
        for raw in listed:
            item = _compact_sku_token(raw)
            if item == sku_compact:
                return True
            item_suf = _sku_control_suffix(item)
            item_stem = item[: -len(item_suf)] if item_suf else item
            # Same stem + same control family (D↔DS, A↔AS, DS↔DST).
            if item_stem == sku_stem and item_suf and sku_suf and _control_suffix_family(item_suf) == sku_fam:
                return True
            # Paren ``SA10MU24-DS/DST`` lists DS; DST is same stem family.
            if (
                item_stem == sku_stem
                and item_suf in {"ds", "dst"}
                and sku_suf
                in {
                    "ds",
                    "dst",
                }
            ):
                return True
        return False

    if short is not None:
        stem = short.group("stem").casefold()
        sufs = {short.group("a").casefold(), short.group("b").casefold()}
        if sku_stem != _compact_sku_token(stem):
            return False
        if sku_suf in sufs:
            return True
        return any(_control_suffix_family(s) == sku_fam for s in sufs)
    return None


def rewrite_analogs_headings_for_sku(text: str, sku_code: str) -> str:
    """Rewrite edition headings to the current article only.

    ``Для Hoocon DA2MU230-DS/DA2MU230-AS (230В):`` →
    ``Для Hoocon DA2MU230-DS (230В):`` when ``sku_code`` is ``DA2MU230-DS``.

    ``Аналоги 24В (SA10MU24-DS/DST):`` → ``Аналоги для SA10MU24-DS (24В):``.
    """
    code = (sku_code or "").strip()
    if not text or not code:
        return text
    volt = _sku_voltage_token(code)
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        volt_match = _ANALOGS_VOLTAGE_HEADER_RE.match(stripped)
        if volt_match is not None:
            band = volt_match.group("volt")
            rebuilt = f"Аналоги для {code} ({band}В)"
            if stripped.endswith(":"):
                rebuilt = f"{rebuilt}:"
            out.append(rebuilt)
            continue
        match = _ANALOGS_EDITION_HEADER_RE.match(stripped)
        if match is None:
            out.append(line)
            continue
        body = match.group("body")
        # Skip non-edition titles («Список аналогов для привода…»).
        if not _ANALOGS_FULL_CODE_RE.search(body) and not _ANALOGS_SHORT_SLASH_RE.search(
            re.sub(r"\s+", "", body),
        ):
            out.append(line)
            continue
        prefix = match.group("prefix")
        tail = match.group("tail") or ""
        if not tail and volt:
            tail = f" ({volt}В)"
        if prefix.casefold().startswith("аналоги"):
            rebuilt = f"Аналоги для {code}{tail}"
        elif "hoocon" in prefix.casefold():
            rebuilt = f"Для Hoocon {code}{tail}"
        else:
            rebuilt = f"Для {code}{tail}"
        if stripped.endswith(":"):
            rebuilt = f"{rebuilt}:"
        out.append(rebuilt)
    return "\n".join(out)


def filter_analogs_for_sku(text: str, sku_code: str) -> str:
    """Keep analog blocks that mention this SKU edition.

    Tilda pages list analogs per edition (``DA3FU230-DS``, ``DA3FU24-DS``,
    ``Аналоги для DA4MU24-A/AS``, ``Для Hoocon DA2MU230-DS/…``, or SAMU
    ``Аналоги 24В (SA10MU24-DS/DST)``). When no edition marker matches, return
    the full text unchanged.

    Headings that list several articles are rewritten to the current
    ``sku_code`` so each PDP shows «свои» аналоги.

    Args:
        text: Full «Аналоги» tab text.
        sku_code: Edition code, e.g. ``da3fu230-ds``.

    Returns:
        Filtered plain text (one edition + shared footnotes).
    """
    if not text or not text.strip():
        return ""
    code = (sku_code or "").strip()
    if not code:
        return text.strip()

    needles = _analogs_edition_needles(code)
    if not needles:
        return text.strip()

    lines = text.replace("\xa0", " ").splitlines()
    blocks: list[list[str]] = [[]]
    header_re = re.compile(
        r"(?i)^(основные характеристики|общие характеристики|аналоги привода|"
        r"аналоги для|аналоги\s+\d|аналоги\s+[a-z]|важные параметры)\b"
        r"|^для\s+(?:hoocon\s+)?[a-z]{2,}\d"
        r"|^[A-Z]{2,}\d+[A-Z]*\d*(?:-|\s|$)",
    )
    shared_re = re.compile(
        r"(?i)^(основные характеристики аналогов|общие характеристики аналогов|важно)\b",
    )
    # Series-wide blurb after edition lists — not SKU-specific.
    drop_re = re.compile(
        r"(?i)^все перечисленные модели\b|^аналоги\s+.+\s+и\s+[a-z]{2,}\d",
    )
    for line in lines:
        stripped = line.strip()
        starts = (
            bool(header_re.search(stripped))
            or bool(shared_re.match(stripped))
            or bool(drop_re.match(stripped))
            or bool(_ANALOGS_VOLTAGE_HEADER_RE.match(stripped))
            or bool(_ANALOGS_MULTI_VOLT_OVERVIEW_RE.match(stripped))
        )
        if starts and blocks[-1] and any(x.strip() for x in blocks[-1]):
            blocks.append([])
        blocks[-1].append(line)

    matched: list[str] = []
    preamble: list[str] = []
    shared: list[str] = []
    saw_edition = False
    for block in blocks:
        first = next((ln.strip() for ln in block if ln.strip()), "")
        if drop_re.match(first) or _ANALOGS_MULTI_VOLT_OVERVIEW_RE.match(first):
            continue
        if shared_re.match(first):
            shared.extend(block)
            shared.append("")
            continue
        header_match = _sku_matches_analogs_header(code, first)
        if header_match is True:
            saw_edition = True
            matched.extend(block)
            matched.append("")
            continue
        if header_match is False:
            continue
        # No concrete edition list — legacy blob needle match.
        blob = re.sub(r"[\s_\-/]+", "", "\n".join(block).casefold())
        if any(needle in blob for needle in needles):
            saw_edition = True
            matched.extend(block)
            matched.append("")
            continue
        # Intro before the first edition header (title without SKU codes).
        if not saw_edition and not header_re.match(first):
            preamble.extend(block)
            preamble.append("")

    if not matched:
        return rewrite_analogs_headings_for_sku(text.strip(), code)

    out_lines = [*preamble, *matched, *shared]
    filtered = dedupe_description_lines("\n".join(out_lines).strip())
    return rewrite_analogs_headings_for_sku(filtered, code)
