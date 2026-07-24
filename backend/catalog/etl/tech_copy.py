"""Normalize catalog copy to Belimo RU terminology (docs/tech-copy-belimo-ru.md)."""

from __future__ import annotations

import re
from collections.abc import Callable


def _damper_drive_replacer(match: re.Match[str]) -> str:
    """«привод(а) вентиляции» → «привод(а) заслонки», preserve stem case."""
    electro = match.group(1) or ""
    ending = match.group(2) or ""
    original = match.group(0)
    stem = f"{electro}привод{ending}"
    # Preserve leading capital from the matched text.
    if original[0].isupper():
        stem = stem[0].upper() + stem[1:]
    return f"{stem} заслонки"


# Ordered: longer / more specific phrases first.
_Repl = str | Callable[[re.Match[str]], str]
_REPLACEMENTS: tuple[tuple[re.Pattern[str], _Repl], ...] = (
    # Control type (full phrase in prose / titles).
    (
        re.compile(r"плавн\w*\s+управл\w*", re.IGNORECASE),
        "пропорциональное (модулирующее) управление",
    ),
    (
        re.compile(r"\(\s*плавн\w*\s*\)", re.IGNORECASE),
        "(пропорциональное)",
    ),
    (
        re.compile(r"плавн\w*\s+регулир\w*", re.IGNORECASE),
        "пропорциональное (модулирующее) регулирование",
    ),
    (
        re.compile(r"(^|[\n.!?…]|\s[-–—]\s)плавный\s*:", re.IGNORECASE | re.MULTILINE),
        r"\1Пропорциональный:",
    ),
    # Short attribute-style after prose pass may leave duplicates — handled below.
    (
        re.compile(r"открыто\s*/\s*закрыто", re.IGNORECASE),
        "открыто/закрыто",
    ),
    (
        re.compile(r"2\s*/\s*3-позиционн\w*", re.IGNORECASE),
        "2-/3-позиционное",
    ),
    # Protection: IP is degree of enclosure, not insulation class.
    (
        re.compile(r"класс\s+защиты\s*(IP\s*\d+\w*)", re.IGNORECASE),
        r"степень защиты корпуса \1",
    ),
    (
        re.compile(r"класс\s+защиты\s*корпуса\s*(IP\s*\d+\w*)", re.IGNORECASE),
        r"степень защиты корпуса \1",
    ),
    # Object wording in analogs / series blurbs (keep case endings).
    (
        re.compile(r"(электро)?привод(ам|ов|а|ы|е|ом)?\s+вентиляции", re.IGNORECASE),
        _damper_drive_replacer,
    ),
    # Signal units (Russian datasheet style).
    (
        re.compile(r"(\d)\s*VDC\b", re.IGNORECASE),
        r"\1 В=",
    ),
    (
        re.compile(r"(\d)\s*V\s*DC\b", re.IGNORECASE),
        r"\1 В=",
    ),
    (
        re.compile(r"(\d)\s*mA\b"),
        r"\1 мА",
    ),
    # Spacing before units often missing after OCR: 10В= → 10 В=
    (
        re.compile(r"(\d)(В=)"),
        r"\1 \2",
    ),
    (
        re.compile(r"(\d)(мА)\b"),
        r"\1 \2",
    ),
)

# Canonical «Управление» facet / EAV labels (four families).
CONTROL_ON_OFF = "Открыто/закрыто"
CONTROL_FLOATING = "2-/3-позиционное"
CONTROL_MODULATING = "Пропорциональное"
CONTROL_MODBUS = "Modbus RS-485"

# Belimo RU — spring-return DAFU (and similar): no hand crank / override.
# Must never store control-type values (Открыто/закрыто) under this slug.
MANUAL_OVERRIDE_NONE = "отсутствует / не предусмотрено"
# SA..FU fire/smoke manuals: pushbutton gearing latch, self-resetting.
MANUAL_OVERRIDE_BUTTON_SELF_RESET = (
    "редуктор выводится из зацепления при помощи кнопки с самовозвратом, ручная блокировка"
)

# Manufacturer «Attention:» block — docs/tech-copy-belimo-ru.md § Предупреждения.
# Lead with «ВНИМАНИЕ:» then one «–» bullet per point (instruction UI list parser).
MANUAL_SAFETY_ATTENTION_LINES: tuple[str, ...] = (
    "ВНИМАНИЕ:",
    (
        "– Запрещается использовать электропривод заслонки вне указанной области "
        "применения, особенно в авиационной технике."
    ),
    (
        "– Вскрытие корпуса привода разрешено только производителю. Внутри нет "
        "компонентов, которые пользователь может заменять или ремонтировать."
    ),
    (
        "– Устройство содержит электрические и электронные компоненты; утилизация "
        "вместе с бытовыми отходами недопустима. Соблюдайте местные правила "
        "утилизации электрооборудования."
    ),
)
_MANUAL_OVERRIDE_CONTROL_LEAK = frozenset(
    {
        CONTROL_ON_OFF.casefold(),
        CONTROL_FLOATING.casefold(),
        CONTROL_MODULATING.casefold(),
        CONTROL_MODBUS.casefold(),
        "плавное управление",
        "2/3-позиционное",
        "on/off",
        "modbus",
        "rs-485",
    },
)


def normalize_manual_override_value(value: str) -> str:
    """Canon cleanup for «Ручное управление» display values.

    Rejects leaked «Управление» facet labels (``Открыто/закрыто``, etc.).
    Does **not** force spring-return ``отсутствует`` onto series that have a
    real hand crank (DAMU / DA8MQU) — empty / ``without`` / control leaks only.

    Args:
        value: Raw EAV / specs value.

    Returns:
        Cleaned value, or ``отсутствует / не предусмотрено`` for empty /
        control-mode leaks / explicit without.
    """
    raw = " ".join((value or "").split()).strip()
    if not raw:
        return MANUAL_OVERRIDE_NONE
    low = raw.casefold()
    if low in _MANUAL_OVERRIDE_CONTROL_LEAK:
        return MANUAL_OVERRIDE_NONE
    if low in {"нет", "без", "without", "none"}:
        return MANUAL_OVERRIDE_NONE
    if "отсутств" in low or "не предусмотр" in low or low == "without":
        return MANUAL_OVERRIDE_NONE
    # «есть» / «кнопка…» stay as-is (no-spring series with a real override).
    return raw


# Belimo RU — modulating editions (docs/tech-copy-belimo-ru.md).
# Voltage 0(2)...10 is factory default; current 0(4)...20 мА — special order only.
CONTROL_SIGNAL_Y_LABEL = "Управляющий сигнал Y"
FEEDBACK_SIGNAL_U_LABEL = "Обратная связь U"
CONTROL_SIGNAL_Y_CANON = "0(2)...10 В= / 0(4)...20 мА (спецзаказ)"
FEEDBACK_SIGNAL_U_CANON = CONTROL_SIGNAL_Y_CANON
CONTROL_SIGNAL_Y_SLUG = "control-signal"
FEEDBACK_SIGNAL_U_SLUG = "feedback-signal"
# FAQ anchor explaining current-mode special order (Page slug=faq).
SIGNAL_MA_SPECIAL_ORDER_FAQ_PATH = "/faq#signal-ma-special-order"

_FACTORY_SIGNAL_NOTE_RE = re.compile(
    r"\s*\(\s*Заводская установка\s+0\.\.\.10\s*В=\s*\)\s*",
    re.IGNORECASE,
)
_SPECIAL_ORDER_NOTE_RE = re.compile(
    r"\s*\(\s*спецзаказ\s*\)\s*",
    re.IGNORECASE,
)


def normalize_modulating_signal_value(value: str) -> str:
    """Compact Y/U signal: drop factory 0...10 note; mark мА as спецзаказ.

    Factory default is voltage ``0(2)...10 В=``. Current ``0(4)...20 мА`` is
    available only on special order (DIP / factory config).

    Args:
        value: Raw or long attribute value.

    Returns:
        Canon string with спецзаказ note when modulating Y/U ranges match.
    """
    raw = (value or "").strip()
    if not raw:
        return CONTROL_SIGNAL_Y_CANON
    compact = _FACTORY_SIGNAL_NOTE_RE.sub(" ", raw)
    compact = _SPECIAL_ORDER_NOTE_RE.sub(" ", compact)
    compact = re.sub(r"\s+", " ", compact).strip()
    compact = re.sub(r"\s*/\s*", " / ", compact)
    # Recognize Belimo modulating ranges (ellipsis variants).
    if re.search(r"0\s*\(\s*2\s*\)\s*\.\.\.?\s*10", compact) and re.search(
        r"0\s*\(\s*4\s*\)\s*\.\.\.?\s*20",
        compact,
    ):
        return CONTROL_SIGNAL_Y_CANON
    return compact or CONTROL_SIGNAL_Y_CANON


def is_proportional_control(value: str) -> bool:
    """True if «Управление» is modulating / пропорциональное."""
    return bool(re.search(r"пропорциональн", (value or "").casefold()))


_CONTROL_VALUE_MAP: dict[str, str] = {
    "плавное управление": CONTROL_MODULATING,
    "пропорциональное (модулирующее)": CONTROL_MODULATING,
    "пропорциональное": CONTROL_MODULATING,
    "открыто/закрыто": CONTROL_ON_OFF,
    "открыто / закрыто": CONTROL_ON_OFF,
    "вкл./выкл. (on/off)": CONTROL_ON_OFF,
    "вкл/выкл": CONTROL_ON_OFF,
    "on/off": CONTROL_ON_OFF,
    "2/3-позиционное": CONTROL_FLOATING,
    "2/3-позиционный": CONTROL_FLOATING,
    "2-/3-позиционное": CONTROL_FLOATING,
    "modbus rs-485": CONTROL_MODBUS,
    "modbus": CONTROL_MODBUS,
    "rs-485": CONTROL_MODBUS,
    "связь по интерфейсу rs-485 (modbus)": CONTROL_MODBUS,
}

# Spring-return / fire / smoke — typically ON/OFF (открыто/закрыто).
_CONTROL_ON_OFF_CATEGORY_SLUGS = frozenset(
    {
        "elektroprivody-s-pruzhinnym-vozvratom",
        "elektroprivody-protivopozharnye-i-dymovye",
        "elektroprivody-dlya-klapanov-dymoudaleniya",
    },
)

# Slugs that contain «управл» in the Russian name but are NOT control-mode.
_NOT_CONTROL_MODE_SLUGS = frozenset(
    {
        "manual-override",
        "control-signal",
        "feedback-signal",
    },
)


def is_control_mode_attribute(*, name: str = "", slug: str = "") -> bool:
    """True for «Управление» (control mode), not manual override / Y / U signals.

    Substring ``управл`` matches «Ручное управление» and «Управляющий сигнал»;
    callers must use this helper instead of a bare ``\"управл\" in name`` check.

    Args:
        name: Attribute.name (any case).
        slug: Attribute.slug when known.

    Returns:
        Whether the row is the control-mode facet/EAV.
    """
    s = (slug or "").casefold().strip()
    if s in _NOT_CONTROL_MODE_SLUGS:
        return False
    if s == "control":
        return True
    n = (name or "").casefold().strip()
    if not n or "ручн" in n:
        return False
    if "управляющ" in n or "сигнал" in n or "обратная связь" in n:
        return False
    return n == "управление" or n.startswith("управление ")


def normalize_tech_copy(text: str) -> str:
    """Apply Belimo RU glossary replacements to free-form catalog text.

    Args:
        text: Description, specs, instructions, name, etc.

    Returns:
        Normalized text (empty string unchanged).
    """
    if not text or not text.strip():
        return text
    out = text
    for pattern, repl in _REPLACEMENTS:
        out = pattern.sub(repl, out)
    # Title-case fix after lowercase regex replace mid-sentence is OK for
    # Russian; restore capital after sentence start / list dash.
    out = _capitalize_glossary_phrases(out)
    return out


def normalize_control_attribute_value(
    value: str,
    *,
    sku_code: str | None = None,
    category_slug: str | None = None,
) -> str:
    """Normalize «Управление» to a canonical facet label.

    Canonical set: ``Открыто/закрыто``, ``2-/3-позиционное``, ``Пропорциональное``,
    ``Modbus RS-485``.

    Args:
        value: Raw EAV value.
        sku_code: Edition code (``da5fu24-d``, ``HVD24-5``, ``H8205-LAV280-24M``).
        category_slug: Product category slug for spring/fire ON/OFF heuristics.

    Returns:
        One of the canonical labels (or lightly cleaned original).
    """
    raw = " ".join((value or "").split())
    if not raw:
        return raw
    low = raw.casefold()

    mapped = _CONTROL_VALUE_MAP.get(low)
    if mapped == CONTROL_MODBUS or re.search(r"modbus|rs\s*-?\s*485", low):
        return CONTROL_MODBUS

    if mapped == CONTROL_MODULATING or re.search(
        r"пропорциональн|модулир|плавн",
        low,
    ):
        return CONTROL_MODULATING

    from catalog.etl.sku_variant import parse_sku_variant

    variant = parse_sku_variant(sku_code or "")
    if variant.control == "modbus":
        return CONTROL_MODBUS
    if variant.control == "modulating":
        return CONTROL_MODULATING

    code = (sku_code or "").strip().upper()
    cat = (category_slug or "").strip().casefold()
    # Spring/fire (FU/SA) and HVD: Tilda often stores «2-/3-позиционное» for
    # what Belimo RU facets as Открыто/закрыто. Air no-spring (-d MU) stays floating.
    is_on_off_family = bool(
        cat in _CONTROL_ON_OFF_CATEGORY_SLUGS
        or code.startswith("HVD")
        or code.startswith("SA")
        or re.match(r"SA\d", code)
        or "FU" in code
    )

    if (
        mapped == CONTROL_ON_OFF
        or re.search(r"открыто|закрыто|вкл\.?\s*/\s*выкл|on\s*/\s*off", low)
        or is_on_off_family
    ):
        if variant.control not in {"modulating", "modbus"}:
            return CONTROL_ON_OFF

    # Prefer SKU-code control family over Tilda's «2-/3» label (see is_on_off_family).
    if variant.control == "on_off":
        return CONTROL_ON_OFF if is_on_off_family else CONTROL_FLOATING

    if mapped == CONTROL_FLOATING or re.search(r"2\s*-?\s*/\s*3|позицион", low):
        return CONTROL_FLOATING

    if mapped:
        return mapped
    return normalize_tech_copy(raw)


# Belimo RU nominal voltage (docs/tech-copy-belimo-ru.md).
VOLTAGE_24_CANON = "AC/DC 24 В, 50/60 Гц"
VOLTAGE_230_CANON = "AC 100…240 В, 50/60 Гц"

_VOLTAGE_230_RE = re.compile(
    r"(?:^|[^0-9])230(?:\s*[вv]|[^0-9]|$)|100\s*[.\-…−–—]+\s*240",
    re.IGNORECASE,
)
_VOLTAGE_24_RE = re.compile(
    r"(?:ac\s*/\s*dc)|(?:^|[^0-9])24(?:\s*[вv]|в\b|,|\s|$)",
    re.IGNORECASE,
)


def detect_voltage_family(value: str) -> str | None:
    """Infer ``24`` / ``230`` from a free-form voltage string.

    Args:
        value: Raw AttributeValue or facet chip text.

    Returns:
        ``\"24\"``, ``\"230\"``, or ``None`` if unrecognized.
    """
    text = " ".join((value or "").split())
    if not text:
        return None
    # Wide-range / 230 family first (avoids mistaking ranges for 24).
    if _VOLTAGE_230_RE.search(text):
        return "230"
    if _VOLTAGE_24_RE.search(text):
        return "24"
    return None


def normalize_voltage_attribute_value(
    value: str,
    *,
    sku_code: str | None = None,
) -> str:
    """Canonical nominal voltage for facets, cards, and PDP ТТХ.

    Prefers SKU-code family when present (fixes Tilda mislabels such as
    ``sa3fu230-*`` stored as AC/DC 24 В).

    Args:
        value: Raw EAV / facet value.
        sku_code: Optional edition code (``da5fu24-d``, ``sa3fu230-ds``).

    Returns:
        Belimo form ``AC/DC 24 В, 50/60 Гц`` or ``AC 100…240 В, 50/60 Гц``,
        or lightly cleaned original if family cannot be detected.
    """
    raw = " ".join((value or "").split())
    if not raw:
        return raw
    family: str | None = None
    if sku_code:
        from catalog.etl.sku_variant import parse_sku_variant

        family = parse_sku_variant(sku_code).voltage
    if family is None:
        family = detect_voltage_family(raw)
    if family == "24":
        return VOLTAGE_24_CANON
    if family == "230":
        return VOLTAGE_230_CANON
    return normalize_tech_copy(raw)


# Belimo RU: running time unit is «с», not «сек» / «секунд».
_RUNNING_TIME_SEK_RE = re.compile(
    r"(?i)(\d+(?:[.,]\d+)?)\s*сек(?:унд(?:ы|а)?)?\.?\b",
)


def normalize_running_time_value(value: str) -> str:
    """Canonical damper running time: ``сек`` / ``секунд`` → ``с``.

    Examples:
        ``≤ 100 сек`` → ``≤ 100 с``;
        ``≤ 60 с (90°)`` unchanged.

    Args:
        value: Raw EAV / highlight value.

    Returns:
        Normalized running-time string.
    """
    raw = " ".join(str(value).strip().split())
    if not raw:
        return raw
    return _RUNNING_TIME_SEK_RE.sub(r"\1 с", raw)


def attribute_display_unit(value: str, unit: str) -> str:
    """Return unit for UI, or empty if the value already includes it.

    Avoids ``≤ 100 с с`` / ``≤ 100 сек с`` when Attribute.unit is ``с``.

    Args:
        value: Display value (possibly already normalized).
        unit: Attribute.unit from the catalog.

    Returns:
        Unit to append, or ``""``.
    """
    cleaned = (unit or "").strip()
    if not cleaned:
        return ""
    text = value or ""
    if cleaned == "с":
        if re.search(r"(?<!\w)с(?!\w)", text):
            return ""
        if re.search(r"(?i)(?<!\w)сек(?:унд(?:ы|а)?)?\.?(?!\w)", text):
            return ""
        return cleaned
    if cleaned.casefold() in text.casefold():
        return ""
    return cleaned


def _capitalize_glossary_phrases(text: str) -> str:
    """Capitalize glossary phrases after start of line / sentence / dash list."""

    def _cap(match: re.Match[str]) -> str:
        prefix = match.group(1)
        phrase = match.group(2)
        return f"{prefix}{phrase[0].upper()}{phrase[1:]}"

    phrases = (
        "пропорциональное \\(модулирующее\\) управление",
        "пропорциональное \\(модулирующее\\) регулирование",
        "пропорциональное \\(модулирующее\\)",
        "степень защиты корпуса",
        "привод заслонки",
        "электропривод заслонки",
        "2-/3-позиционное",
    )
    out = text
    for phrase in phrases:
        out = re.sub(
            rf"(^|[\n.!?…]|\s[-–—]\s)({phrase})",
            _cap,
            out,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    return out
