"""SKU heading / lead / echo-stripping for catalog copy.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_HEADING_AUX_ABSENT = re.compile(
    r"\s*[-–—]\s*(?:нет|no|без|отсутствует)\s*$",
    re.IGNORECASE,
)
_HEADING_AUX_PRESENT = re.compile(
    r"\s*[-–—]\s*(?:да|yes|есть)\s*$",
    re.IGNORECASE,
)
# Store CSV: ``SERIES | 8Нм Product name - 8 Нм - 230 В - Control - Нет``
_HEADING_PIPE = re.compile(
    r"^(?P<code>[^|]+)\|\s*"
    r"(?:(?P<nm>[\d.,]+)\s*нм\s+)?"
    r"(?P<body>.+)$",
    re.IGNORECASE,
)
_HEADING_EDITION_TRAILER = re.compile(
    r"\s*[-–—]\s+\d+[.,]?\d*\s*нм\b.*$",
    re.IGNORECASE,
)
# Store CSV valve trailer: ``- 2-ходовый - 15 - 1,6`` (ways / DN / Kvs).
_HEADING_VALVE_TRAILER = re.compile(
    r"\s*[-–—]\s*\d+-ходов\w*\s*[-–—]\s*\d+\s*[-–—]\s*[\d.,]+\s*$",
    re.IGNORECASE,
)
# Control-type phrases baked into the body before the edition trailer
# (HVA/HVD series): «пропорциональное управление», «управление 2-/3-позиционное»,
# «позиционное управление», «Плавное управление», «Открыто/Закрыто».
# Stripped from the end of the body; control type belongs in highlights.
_HEADING_CONTROL_TAIL = re.compile(
    r"\s+"
    r"(?:"
    r"(?:пропорциональн\w*|плавн\w*|позицион\w*)\s+управление"
    r"|управление\s+(?:2-?/?3?-?позицион\w*|позицион\w*)"
    r"|2-?/?3?-?позицион\w*"
    r"|открыт\w*/?\s*закрыт\w*"
    r")"
    r"\s*$",
    re.IGNORECASE,
)
# Canonical word order for fast-acting springless actuators: «ускоренного
# срабатывания без возвратной пружины» (matches DA8MQU canon). HVA-5Q raw
# stores the reverse order; swap so the family reads the same across series.
_HEADING_REORDER_FAST = re.compile(
    r"\bбез\s+возвратной\s+пружины\s+ускоренного\s+срабатывания\b",
    re.IGNORECASE,
)
# Bare product noun → SEO-valuable «Электропривод» (matches category names
# «Электроприводы …»). Only matches a standalone lead word so mid-body
# occurrences (none currently) are untouched.
_HEADING_PRIVOD_TO_ELEKTRO = re.compile(r"^привод\b", re.IGNORECASE)
_LEAD_SKIP = re.compile(
    r"^(?:[-–—•*]|\d+[.)])\s*|"
    r"^(?:номинальн|управлен|питание|сигнал|основные|характеристик)",
    re.IGNORECASE,
)


def _norm_heading_phrase(text: str) -> str:
    """Normalize a phrase for heading/description echo comparison."""
    s = " ".join((text or "").casefold().split())
    if "|" in s:
        s = s.split("|", 1)[-1].strip()
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return " ".join(s.split())


def _heading_article(sku_code: str, fallback: str) -> str:
    """Unique left-side article for H1 / cards.

    Ball valves: ``8100-bv215a`` → ``BV215A``, ``8100Q-bv265`` → ``BV265``.
    Actuators: keep ``sku_code``.
    """
    code = (sku_code or "").strip()
    if not code:
        return fallback
    m_q = re.match(r"(?i)^8100q-(.+)$", code)
    if m_q:
        return m_q.group(1).upper()
    m = re.match(r"(?i)^8100-(.+)$", code)
    if m:
        return m.group(1).upper()
    return code


def _strip_control_tail(body: str) -> str:
    """Drop a trailing control-type phrase baked into the heading body.

    HVA/HVD raw names embed «пропорциональное управление» / «управление
    2-/3-позиционное» / «позиционное управление» before the edition trailer.
    Control type belongs in highlights, not H1 — but restore the original
    body when stripping would leave a bare product noun («Привод …» →
    «Привод»), which is too generic for a unique title.

    Args:
        body: Body text after pipe split and edition/valve trailer strip.

    Returns:
        Body without the trailing control phrase, or the original body when
        the result would be too short.
    """
    if not body:
        return body
    stripped = _HEADING_CONTROL_TAIL.sub("", body).strip(" |-–—")
    if not stripped or len(stripped.split()) < 2:
        return body
    return stripped


def format_sku_heading_name(
    name: str,
    *,
    description: str = "",
    sku_code: str = "",
    kvs: str = "",
) -> str:
    """Clean store CSV title for H1 / cards: unique article + product type.

    Strips edition trailer (``- 8 Нм - 230 В - управление - Нет/Да``),
    valve facet trailer (``- 2-ходовый - 15 - 1,6``), optional ``NНм`` after
    ``|``, and control-type phrases baked into the body (``пропорциональное
    управление``, ``управление 2-/3-позиционное``). Normalizes the bare
    product noun to SEO-valuable «Электропривод» and unifies the word order
    for fast-acting springless actuators. When ``sku_code`` is set, the left
    side is the article (unique per SKU). Ball valves append ``Kvs`` when
    provided.

    Args:
        name: Raw ``SKU.name`` from import.
        description: Unused; kept for call-site compatibility.
        sku_code: SKU article for unique heading prefix.
        kvs: Optional Kvs value for valve titles.

    Returns:
        Display title, e.g. ``DA8MU24-D | Электропривод воздушный…`` or
        ``BV215A | Шаровой кран 2-ходовый DN 15, Kvs 1,6``.
    """
    _ = description  # call-site compat; aux lives in highlights
    from catalog.etl.tech_copy import normalize_tech_copy

    text = normalize_tech_copy(" ".join((name or "").split()))
    if not text:
        return (sku_code or "").strip()

    # Product titles: «пропорциональное управление» without Belimo parenthetical.
    text = re.sub(
        r"\s*\(\s*модулирующ\w*\s*\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = " ".join(text.split())

    if _HEADING_AUX_ABSENT.search(text):
        text = _HEADING_AUX_ABSENT.sub("", text).rstrip(" -–—")
    if _HEADING_AUX_PRESENT.search(text):
        text = _HEADING_AUX_PRESENT.sub("", text).rstrip(" -–—")

    code = ""
    body = text
    pipe = _HEADING_PIPE.match(text)
    if pipe:
        code = pipe.group("code").strip()
        body = pipe.group("body").strip()
        body = _HEADING_EDITION_TRAILER.sub("", body).strip()
        body = _HEADING_VALVE_TRAILER.sub("", body).strip()
        body = re.sub(
            r"\s*[-–—]\s*(?:пропорциональн\w*.*|2-/3-позицион\w*|открыто.*)$",
            "",
            body,
            flags=re.IGNORECASE,
        ).strip()
    else:
        body = _HEADING_EDITION_TRAILER.sub("", text).strip()
        body = _HEADING_VALVE_TRAILER.sub("", body).strip()

    article = _heading_article(sku_code, code)
    # Drop edition echo inside body (``(HVA230-5)`` or bare code) *before*
    # stripping the control-type tail — otherwise ``…управление (HVA230-5)``
    # leaves empty ``()`` after the code is removed.
    if article and body:
        body = re.sub(
            rf"\s*\(\s*{re.escape(article)}\s*\)",
            "",
            body,
            flags=re.IGNORECASE,
        )
        body = re.sub(
            re.escape(article),
            "",
            body,
            flags=re.IGNORECASE,
        ).strip(" |-–—")
    body = _strip_control_tail(body)
    body = re.sub(r"\(\s*\)", "", body)

    # Torque belongs in highlights — never echo «N Нм» in the display title.
    # Also drop a preceding comma from canon titles like «…пружины, 2 Нм».
    body = re.sub(
        r"(?:,\s*|\s+|^)\d+[.,]?\d*\s*нм\b",
        "",
        body,
        flags=re.IGNORECASE,
    )
    body = _HEADING_REORDER_FAST.sub(
        "ускоренного срабатывания без возвратной пружины",
        body,
    )
    body = _HEADING_PRIVOD_TO_ELEKTRO.sub("Электропривод", body, count=1)
    body = " ".join(body.split()).strip(" |-–—,")

    kvs_val = " ".join((kvs or "").split())
    if kvs_val and body and "kvs" not in body.casefold():
        body = f"{body}, Kvs {kvs_val}"

    if article and body:
        return f"{article} | {body}"
    return article or body


def extract_sku_lead(description: str, *, max_len: int = 220) -> str:
    """Pick the first prose sentence(s) from a structured description.

    Skips bullet lists and section headers (``Управление:``). Prefer the
    application blurb, e.g. «Электропривод воздушный… Используется в…».

    Args:
        description: SKU / product description text.
        max_len: Soft cap for hero lead.

    Returns:
        Plain lead text or empty string.
    """
    from catalog.etl.tech_copy import normalize_tech_copy

    if not description or not description.strip():
        return ""
    text = normalize_tech_copy(description.replace("\xa0", " "))
    candidates: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or len(line) < 40:
            continue
        if _LEAD_SKIP.search(line):
            continue
        if line.endswith(":"):
            continue
        candidates.append(line)
    if not candidates:
        return ""
    # Prefer the longest prose block (usually the product blurb).
    lead = max(candidates, key=len)
    # If the blurb is «Name. Application…», keep only the application sentence.
    parts = re.split(r"(?<=[.!?…])\s+", lead)
    if len(parts) >= 2:
        for part in parts[1:]:
            if re.match(
                r"(?i)^(?:используется|применяется|предназначен|для\b)",
                part,
            ):
                lead = part
                break
        else:
            # Drop the first sentence when it is a product-type restatement.
            if len(parts[0]) < 120 and len(parts[1]) > 20:
                lead = " ".join(parts[1:])
    if len(lead) <= max_len:
        return lead
    cut = lead[: max_len - 1].rsplit(" ", 1)[0]
    return f"{cut}…" if cut else lead[:max_len]


_LEAD_FOR_PURPOSE = re.compile(
    r"(?i)^(?:электро)?привод\s+(?P<head>.+?)\s+для\s+(?P<purpose>.+?)"
    r"(?:\s+с\s+(?P<with>.+))?$",
)


def paraphrase_sku_lead(lead: str) -> str:
    """Reword hero lead for the Описание tab (avoid exact SEO duplicate).

    Args:
        lead: Hero blurb already shown under H1.

    Returns:
        Slightly rephrased sentence(s), or empty when ``lead`` is blank.
    """
    text = " ".join((lead or "").split()).strip().rstrip(" .")
    if not text:
        return ""

    match = _LEAD_FOR_PURPOSE.match(text)
    if match is not None:
        head = match.group("head").strip()
        purpose = match.group("purpose").strip()
        with_feat = (match.group("with") or "").strip()
        bits = [f"Применяется для {purpose}"]
        if with_feat:
            bits.append(f"в исполнении с {with_feat}")
        first = "; ".join(bits) + "."
        if re.search(r"\d", head):
            return f"{first} Номинальный крутящий момент — {head}."
        rest = head[:1].upper() + head[1:] if head else ""
        return f"{first} {rest}.".strip() if rest else first

    # Generic: change surface form without inventing new specs.
    body = text[:1].lower() + text[1:] if text else text
    return f"Назначение модели: {body}."


def strip_lead_duplicate_lines(description: str, lead: str) -> str:
    """Remove description lines that only restate the hero lead.

    Args:
        description: SKU description body.
        lead: Hero lead already rendered under H1.

    Returns:
        Description without exact / near-exact lead restatements.
    """
    if not description or not description.strip() or not lead.strip():
        return description or ""
    lead_n = _norm_heading_phrase(lead)
    if not lead_n:
        return description
    out: list[str] = []
    for raw in description.replace("\xa0", " ").splitlines():
        stripped = " ".join(raw.split())
        if not stripped:
            out.append(raw)
            continue
        if _LEAD_SKIP.search(stripped) or stripped.endswith(":"):
            out.append(raw)
            continue
        parts = re.split(r"(?<=[.!?…])\s+", stripped)
        kept = [
            part
            for part in parts
            if (pn := _norm_heading_phrase(part)) and not (pn == lead_n or lead_n in pn or pn in lead_n)
        ]
        if not kept:
            continue
        out.append(" ".join(kept))
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out).strip()


def strip_heading_echo_from_description(
    description: str,
    *,
    heading: str = "",
    lead: str = "",
) -> str:
    """Drop opening sentences that repeat H1 / hero lead.

    Args:
        description: Structured SKU description.
        heading: Formatted H1 (series + product type).
        lead: Hero lead already shown under H1.

    Returns:
        Description without echoed opening prose.
    """
    if not description or not description.strip():
        return ""
    heading_n = _norm_heading_phrase(heading)
    lead_n = _norm_heading_phrase(lead)
    lines = description.replace("\xa0", " ").splitlines()
    out: list[str] = []
    stripped_prose = False
    for raw in lines:
        line = raw.rstrip()
        stripped = " ".join(line.split())
        # Skip thin opening one-liners that only restate card ТТХ
        # («привод 10 Нм управления 2-/3-позиционное…»).
        if (
            not stripped_prose
            and stripped
            and not _LEAD_SKIP.search(stripped)
            and re.match(r"(?i)^привод\s+\d+", stripped)
            and len(stripped) < 140
        ):
            continue
        if not stripped_prose and stripped and not _LEAD_SKIP.search(stripped):
            parts = re.split(r"(?<=[.!?…])\s+", stripped)
            kept: list[str] = []
            for part in parts:
                pn = _norm_heading_phrase(part)
                if not pn:
                    continue
                if lead_n and (pn == lead_n or lead_n in pn or pn in lead_n):
                    continue
                if heading_n and (
                    pn == heading_n or heading_n in pn or pn in heading_n or _phrases_echo(heading_n, pn)
                ):
                    continue
                kept.append(part)
            stripped_prose = True
            if kept:
                out.append(" ".join(kept))
            continue
        out.append(line)
    # Drop leading blank lines after strip.
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out).strip()


def _phrases_echo(heading: str, sentence: str) -> bool:
    """True when sentence restates the product-type heading (near-duplicate)."""
    if len(heading) < 24 or len(sentence) < 24:
        return False
    h_tokens = set(heading.split())
    s_tokens = set(sentence.split())
    if len(h_tokens) < 4 or len(s_tokens) < 4:
        return False
    overlap = len(h_tokens & s_tokens) / min(len(h_tokens), len(s_tokens))
    # «электропривод воздушный…» vs «электропривод воздушной заслонки…»
    return overlap >= 0.55 and ("электропривод" in h_tokens or "привод" in h_tokens or "кран" in h_tokens)


_BULLET_ATTR_LINE = re.compile(
    r"^(?:[-–—•*]|\d+[.)])\s*(?P<body>.+)$",
)

# Decorative markers before bare titles (``✅ Преимущества серии``).
_TITLE_DECOR_RE = re.compile(r"^[✅⚠❗●•]\s*")

# Bare subsection titles (no colon) that may become empty after EAV strip.
_BARE_SUB_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"промышленные объекты|общественные здания|специальные сооружения|"
    r"интеграция|температурный режим|класс защиты|уровень шума|"
    r"особенности(?:\s+приводов)?|вспомогательные компоненты|запреты"
    r")$",
    re.IGNORECASE,
)

# Any bare section title (major or sub) — used when scanning for "next header".
_BARE_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"основные особенности|области применения|область применения|сфера применения|"
    r"преимущества|отличительные преимущества|"
    r"конкурентные преимущества(?:\s+перед\s+аналогами)?|"
    r"функциональные особенности|технические возможности|"
    r"ключевые характеристики|конструктивные особенности|"
    r"эксплуатационные параметры|безопасность и сертификация|"
    r"важные замечания(?:\s+по\s+эксплуатации)?|"
    r"технические характеристики|комплектация|назначение|"
    r"назначение и принцип работы|"
    r"требования безопасности и эксплуатации|"
    r"особенности восстановления после пожара|заключение|"
    r"общие характеристики аналогов|преимущества серии(?:\s.+)?|"
    r"промышленные объекты|общественные здания|специальные сооружения|"
    r"интеграция|температурный режим|класс защиты|уровень шума|"
    r"особенности(?:\s+приводов)?|вспомогательные компоненты|запреты"
    r")$",
    re.IGNORECASE,
)


def strip_attribute_echo_from_text(
    text: str,
    attributes: Iterable[dict[str, str]],
) -> str:
    """Remove bullet lines that repeat structured AttributeValue rows.

    Keeps section headers and prose that are not covered by EAV. Orphan
    headers (no remaining body) are dropped. Soft-wrapped continuation
    lines after a removed bullet are dropped too.

    Args:
        text: ``specs_text`` or description with bullets.
        attributes: ``[{name, value}]`` (unit optional / ignored).

    Returns:
        Filtered text, possibly empty.
    """
    rows = list(attributes)
    if not text or not text.strip() or not rows:
        return (text or "").strip()

    names: set[str] = set()
    values: set[str] = set()
    for row in rows:
        name_n = _norm_heading_phrase(str(row.get("name") or ""))
        value_n = _norm_heading_phrase(str(row.get("value") or ""))
        if name_n:
            names.add(name_n)
        if value_n:
            values.add(value_n)
            bare = re.sub(r"\s+(нм|мм|кг|м²|с|в|°c|дб.?a?)\s*$", "", value_n)
            if bare and bare != value_n:
                values.add(bare)

    lines = text.replace("\xa0", " ").splitlines()
    kept: list[str] = []
    skip_continuations = False
    for raw in lines:
        stripped = " ".join(raw.split())
        if not stripped:
            kept.append("")
            skip_continuations = False
            continue
        bullet = _BULLET_ATTR_LINE.match(stripped)
        if bullet:
            body = bullet.group("body").strip()
            if _bullet_echoes_attribute(body, names=names, values=values):
                skip_continuations = True
                continue
            skip_continuations = False
            kept.append(raw.rstrip())
            continue
        if skip_continuations and not stripped.endswith(":"):
            continue
        skip_continuations = False
        kept.append(raw.rstrip())

    return _drop_orphan_section_headers(kept)


def _bullet_echoes_attribute(
    body: str,
    *,
    names: set[str],
    values: set[str],
) -> bool:
    """True if a bullet body is already represented as an attribute row."""
    if ":" in body:
        label, _, value = body.partition(":")
        label_n = _norm_heading_phrase(label)
        value_n = _norm_heading_phrase(value)
        if label_n and _label_matches_attr_name(label_n, names):
            return True
        if value_n and value_n in values:
            return True
        if "вспомогательн" in label_n and value_n in {
            "нет",
            "отсутствует",
            "без",
            "no",
        }:
            return True
    body_n = _norm_heading_phrase(body)
    if body_n in values:
        return True
    if _bullet_numeric_power_claim(body, names=names):
        return True
    return False


def _has_power_consumption_attr(names: set[str]) -> bool:
    """True when ТТХ already lists consumed power."""
    return any("потребляем" in n or n == "мощность" for n in names)


def _bullet_numeric_power_claim(body: str, *, names: set[str]) -> bool:
    """Drop marketing wattage claims when power is already in ТТХ cards.

    Series copy often says «3−5 Вт в режиме ожидания» while the SKU card
    has a different ``Потребляемая мощность`` — characteristics win.
    """
    if not _has_power_consumption_attr(names):
        return False
    body_l = body.lower().replace("−", "-")
    if "вт" not in body_l or not re.search(r"\d", body_l):
        return False
    return bool(
        re.search(
            r"энергопотреб|режиме ожидания|удержани|потребляем\w*\s+мощност",
            body_l,
        )
    )


def _label_matches_attr_name(label_n: str, names: set[str]) -> bool:
    """Match «Площадь обслуживаемой заслонки» to «Площадь заслонки (м²)»."""
    stop = {"м", "мм", "кг", "с", "в", "нм", "до", "макс", "min", "max"}
    qualifiers = frozenset(
        {
            "номинальное",
            "номинальный",
            "рабочее",
            "рабочий",
            "максимальное",
            "максимальный",
        },
    )
    for name_n in names:
        if label_n == name_n:
            return True
        # «номинальное напряжение» ↔ «напряжение»; not «ручное управление».
        if name_n and label_n.endswith(name_n):
            prefix = label_n[: -len(name_n)].strip(" -–—")
            if not prefix or prefix in qualifiers:
                return True
        lt = {t for t in label_n.split() if t not in stop and len(t) > 2}
        nt = {t for t in name_n.split() if t not in stop and len(t) > 2}
        if len(nt) >= 2 and len(lt & nt) >= 2:
            return True
        if len(nt) >= 2 and nt <= lt:
            return True
    return False


def _bare_section_title(stripped: str) -> str:
    """Strip emoji / trailing colon for bare-title matching."""
    return _TITLE_DECOR_RE.sub("", stripped).rstrip(":").strip()


def _is_any_section_header(stripped: str) -> bool:
    """True for ``Title:`` and known bare major/sub section titles."""
    if not stripped or _BULLET_ATTR_LINE.match(stripped):
        return False
    if stripped.endswith(":"):
        return True
    return bool(_BARE_SECTION_HEADER_RE.match(_bare_section_title(stripped)))


def _is_orphan_candidate_header(stripped: str) -> bool:
    """Headers we may drop when empty — colon titles and bare *sub* titles.

    Major bare group headers (``Эксплуатационные параметры``) stay even when
    the next line is a nested ``Класс защиты:`` subsection.
    """
    if not stripped or _BULLET_ATTR_LINE.match(stripped):
        return False
    if stripped.endswith(":"):
        return True
    return bool(_BARE_SUB_SECTION_HEADER_RE.match(_bare_section_title(stripped)))


def _drop_orphan_section_headers(lines: list[str]) -> str:
    """Drop headers that have no content until the next header / EOF.

    Bare subsection titles (``Температурный режим``) are included so EAV
    echo-stripping does not leave an empty heading above the next section.
    """
    cleaned: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = " ".join(line.split())
        if _is_orphan_candidate_header(stripped):
            j = i + 1
            has_body = False
            while j < len(lines):
                nxt = " ".join(lines[j].split())
                if not nxt:
                    j += 1
                    continue
                if _is_any_section_header(nxt):
                    break
                has_body = True
                break
            if not has_body:
                i += 1
                continue
        cleaned.append(line)
        i += 1

    # Collapse excess blank lines.
    out: list[str] = []
    blank = 0
    for line in cleaned:
        if not line.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(line)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)
