"""Auxiliary switch (SPDT) value helpers.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re

AUX_SWITCH_NONE = "Нет"
AUX_SWITCH_SPDT_1 = "SPDT-1"
AUX_SWITCH_SPDT_2 = "SPDT-2"

_AUX_ABSENT = frozenset({"нет", "no", "false", "0", "-", "без", "отсутствует"})
_AUX_PRESENT = frozenset({"да", "yes", "true", "1", "есть"})


def _looks_like_aux_value(value: str) -> bool:
    """True if text is a boolean / SPDT aux-switch label."""
    low = " ".join((value or "").casefold().split())
    if not low:
        return False
    if low in _AUX_ABSENT or low in _AUX_PRESENT:
        return True
    return bool(re.search(r"spdt", low, re.I))


def aux_spdt_count_from_sku(sku_code: str) -> int | None:
    """Infer SPDT count from edition suffix (Belimo DS=1, AS/S=2).

    H81 factory kits are an exception: catalog wiring shows two limit switches
    (a + b) on both ``-AS`` and ``-DS``.

    Args:
        sku_code: Edition code, e.g. ``da5fu24-ds``, ``H8101-BV215A-24AS``.

    Returns:
        ``0`` (none), ``1``, ``2``, or ``None`` if unknown.
    """
    code = (sku_code or "").strip().lower().replace(" ", "")
    if not code:
        return None
    # H8205-LAV: ``S`` / ``ST`` before voltage → aux present (catalog wiring a+b).
    if re.match(r"h8205-lav", code):
        if re.search(r"lav\d+(?:st|s)-(?:24|230)[adm]$", code):
            return 2
        if re.search(r"lav\d+(?:t)?-(?:24|230)[adm]$", code):
            return 0
        return None
    # H81 factory kits: catalog shows two aux limit switches (a + b) on -AS/-DS.
    # Edition is glued to voltage (…-24AS / …-230DS), not a bare «-as» suffix.
    if re.match(r"h81(?:01|02|03|04|05|06|07|08|21|22)-bv", code):
        if re.search(r"(?:24|230)(?:as|ds)$", code):
            return 2
        if re.search(r"(?:24|230)(?:a|d)$", code):
            return 0
        return None
    # DA..MU (no spring): manuals — DA2 = 1 group on AS/DS; DA4+ = 2 groups.
    # Must run before the generic «-as → 2» Belimo rule (DA2MU*-AS is SPDT-1).
    if re.match(r"da2mu(?!q)", code):
        if code.endswith("-as") or code.endswith("-ds"):
            return 1
        if code.endswith("-a") or code.endswith("-d"):
            return 0
        return None
    if re.match(r"da(?:4|6|8|16|24|32)mu(?!q)", code):
        if code.endswith("-as") or code.endswith("-ds"):
            return 2
        if code.endswith("-a") or code.endswith("-d"):
            return 0
        return None
    # DA..MQU fast: AS/DS manuals show 2 auxiliary switch groups.
    if re.match(r"da\d+mqu", code):
        if code.endswith("-as") or code.endswith("-ds"):
            return 2
        if code.endswith("-a") or code.endswith("-d"):
            return 0
        return None
    # DA..EU electronic fail-safe: album «DS включает 2 вспомогательных».
    if re.match(r"da\d+eu", code):
        if code.endswith("-ds"):
            return 2
        if code.endswith("-d"):
            return 0
        return None
    if re.search(r"-as(?:$|[^a-z])", code) or code.endswith("-as"):
        return 2
    # SA..FU fire/smoke manuals: «S type include 2 auxiliary switch» (DS/DST).
    if re.match(r"sa\d+fu", code) and (code.endswith("-dst") or code.endswith("-ds")):
        return 2
    # SA..MU smoke (no spring): manuals «-DS Include 2 groups» (DS/DST).
    if re.match(r"sa\d+mu", code) and (code.endswith("-dst") or code.endswith("-ds")):
        return 2
    if re.search(r"-dst(?:$|[^a-z])", code) or code.endswith("-dst"):
        return 1
    if re.search(r"-ds(?:$|[^a-z])", code) or code.endswith("-ds"):
        return 1
    # HVD24S-3F / HVD230ST-5F — fire/smoke F-series: S/ST = 2 aux groups.
    if re.fullmatch(r"hvd(?:24|230)st?-\d+f", code):
        return 2
    # HVA24S-5 / HVD230S-10 — «S» edition = 2 auxiliary switches.
    if re.search(r"(?:hva|hvd)\d*s-?\d", code):
        return 2
    # Bare HVA24-5 / HVD230-40 (no S) — no aux group.
    if re.fullmatch(r"(?:hva|hvd)(?:24|230)-\d+(?:q|qx|qa|p)?", code):
        return 0
    if re.search(r"-a(?:$|[^a-z])", code) or code.endswith("-a"):
        return 0
    if re.search(r"-d(?:$|[^a-z])", code) or code.endswith("-d"):
        return 0
    return None


def normalize_aux_switch_value(
    value: str,
    *,
    sku_code: str | None = None,
    description: str = "",
) -> str:
    """Canonical aux facet / ТТХ: ``Нет`` / ``SPDT-1`` / ``SPDT-2``.

    Args:
        value: Raw EAV (Да / Нет / ``2 SPDT`` / ``SPDT-2``).
        sku_code: Edition code for DS/AS/S count and to fix mislabeled Да.
        description: SKU text that may mention ``1 SPDT`` / ``2 SPDT``.

    Returns:
        One of the three canonical labels.
    """
    raw = " ".join((value or "").split())
    low = raw.casefold()

    def _label(count: int) -> str:
        if count <= 0:
            return AUX_SWITCH_NONE
        if count == 1:
            return AUX_SWITCH_SPDT_1
        return AUX_SWITCH_SPDT_2

    # Edition suffix is authoritative (series texts often say «2 SPDT» for all).
    sku_count = aux_spdt_count_from_sku(sku_code or "")
    if sku_count is not None:
        return _label(sku_count)

    count_match = re.search(r"(?:spdt\s*[-–—]?\s*(\d)|(\d)\s*[-–—]?\s*spdt)", raw, re.I)
    if count_match:
        digit = count_match.group(1) or count_match.group(2)
        return _label(int(digit))

    if low in _AUX_ABSENT:
        return AUX_SWITCH_NONE

    desc_match = re.search(
        r"(?:spdt\s*[-–—]?\s*(\d)|(\d)\s*[-–—]?\s*spdt)",
        description or "",
        re.I,
    )
    if desc_match:
        digit = desc_match.group(1) or desc_match.group(2)
        return _label(int(digit))

    if low in _AUX_PRESENT or "spdt" in low:
        # Legacy «Да» without SKU context — Belimo AS default is two switches.
        return AUX_SWITCH_SPDT_2

    if len(raw) <= 24 and raw:
        return raw
    return AUX_SWITCH_NONE


def format_aux_switch_display(
    value: str,
    *,
    description: str = "",
    sku_code: str | None = None,
) -> str | None:
    """Format auxiliary-switch for full ТТХ table (not catalog cards).

    - Absent / «Нет» → ``None`` (omit the row in PDP attributes).
    - Present → ``SPDT-1`` or ``SPDT-2``.
    Cards / hero use ``normalize_aux_switch_value`` and always show «Нет».

    Args:
        value: Raw AttributeValue (Да / Нет / already ``SPDT-2``).
        description: Optional SKU text to detect switch count.
        sku_code: Edition code (DS=1, AS/S=2).

    Returns:
        Display string or None to hide the row.
    """
    normalized = normalize_aux_switch_value(
        value,
        sku_code=sku_code,
        description=description,
    )
    if normalized == AUX_SWITCH_NONE:
        return None
    if normalized in {AUX_SWITCH_SPDT_1, AUX_SWITCH_SPDT_2}:
        return normalized
    return None
