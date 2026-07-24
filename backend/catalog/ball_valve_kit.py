"""Ball-valve RFQ kit options: compatible drives + auto bracket (BR-M / BR-ML)."""

from __future__ import annotations

import re
from typing import Any, cast

from catalog.etl.series_copy_ball_valves import ball_valve_product_slugs, format_bracket
from catalog.models import SKU, Attribute
from catalog.sku_access import sku_attribute_values, sku_category_slug_or_empty

_FU_DRIVE_RE = re.compile(r"(?i)da\d*fu")
_DRIVE_FAMILY_RE = re.compile(r"(?i)\b(da[a-z0-9]+)\b")
_BALL_VALVE_CATEGORY = "sharovye-krany"
_DRIVE_SUFFIXES: tuple[str, ...] = ("-D", "-DS", "-A", "-AS")


def parse_drive_families(text: str) -> list[str]:
    """Extract drive families from «Совместимый привод» EAV text.

    Args:
        text: e.g. ``DA5FU24, DA6MU24 (−D/−DS/−A/−AS)``.

    Returns:
        Uppercase family codes in first-seen order.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _DRIVE_FAMILY_RE.finditer(text or ""):
        code = match.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def resolve_bracket_for_drive(drive_family: str, *, flanged: bool = False) -> str:
    """Pick bracket SKU for a selected drive family.

    BR-H for flanged ВЧШГ valves; BR-ML only for DA…FU on brass; else BR-M.

    Args:
        drive_family: Base article, e.g. ``DA5FU24`` or ``DA6MU24``.
        flanged: True for DN65+ flanged bodies.

    Returns:
        ``BR-H``, ``BR-ML``, or ``BR-M``.
    """
    if flanged:
        return "BR-H"
    return "BR-ML" if _FU_DRIVE_RE.search(drive_family) else "BR-M"


def is_ball_valve_sku(sku: SKU) -> bool:
    """True when SKU belongs to the ball-valve category or BV product line.

    Uses :func:`sku_category_slug_or_empty` so a missing product/category chain
    yields ``""`` (never ``None``) before the category compare; BV product
    slugs still match when the category FK is incomplete.
    """
    if sku_category_slug_or_empty(sku) == _BALL_VALVE_CATEGORY:
        return True
    product = getattr(sku, "product", None)
    if product is None:
        return False
    return (product.slug or "") in ball_valve_product_slugs()


def _compatible_actuators_text(sku: SKU) -> str:
    for av in sku_attribute_values(sku):
        attr = cast(Attribute, av.attribute)
        slug = (attr.slug or "").casefold()
        name = (attr.name or "").casefold()
        if slug == "compatible-actuators" or ("совместим" in name and "привод" in name):
            return str(av.value or "").strip()
    return ""


def _is_flanged_valve(sku: SKU) -> bool:
    """True when EAV material/connection marks a flanged ВЧШГ body."""
    for av in sku_attribute_values(sku):
        attr = cast(Attribute, av.attribute)
        slug = (attr.slug or "").casefold()
        val = str(av.value or "").casefold()
        if slug == "material" and "вчшг" in val:
            return True
        if slug in {"connection", "thread"} and "фланц" in val:
            return True
    return False


def build_ball_valve_kit_options(sku: SKU) -> dict[str, Any] | None:
    """Build structured RFQ kit picker payload for ball-valve PDP.

    Args:
        sku: Published ball-valve SKU with enriched EAV.

    Returns:
        ``None`` for non-valves, complete H8103/H8104 kits, or when no drives
        are known; otherwise dict with ``drive_families``, ``suffixes``,
        ``bracket_by_drive``, ``bracket_hint``.
    """
    if not is_ball_valve_sku(sku):
        return None
    from catalog.etl.h81_kits import is_h81_kit_sku_code

    if is_h81_kit_sku_code(sku.sku_code or ""):
        return None
    families = parse_drive_families(_compatible_actuators_text(sku))
    if not families:
        return None
    flanged = _is_flanged_valve(sku)
    bracket_by_drive = {family: resolve_bracket_for_drive(family, flanged=flanged) for family in families}
    hint = "BR-H" if flanged else format_bracket(tuple(families))
    return {
        "drive_families": families,
        "suffixes": list(_DRIVE_SUFFIXES),
        "bracket_by_drive": bracket_by_drive,
        "bracket_hint": hint,
    }
