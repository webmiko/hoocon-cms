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

    Args:
        sku_code: Edition code, e.g. ``da5fu24-ds``, ``HVA24S-5``.

    Returns:
        ``0`` (none), ``1``, ``2``, or ``None`` if unknown.
    """
    code = (sku_code or "").strip().lower().replace(" ", "")
    if not code:
        return None
    if re.search(r"-as(?:$|[^a-z])", code) or code.endswith("-as"):
        return 2
    # SA..FU fire/smoke manuals: «S type include 2 auxiliary switch» (DS/DST).
    if re.match(r"sa\d+fu", code) and (code.endswith("-dst") or code.endswith("-ds")):
        return 2
    if re.search(r"-dst(?:$|[^a-z])", code) or code.endswith("-dst"):
        return 1
    if re.search(r"-ds(?:$|[^a-z])", code) or code.endswith("-ds"):
        return 1
    # HVA24S-5 / HVD230S-10 — «S» edition = 2 auxiliary switches.
    if re.search(r"(?:hva|hvd)\d*s-?\d", code):
        return 2
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
