"""Normalize facet values for filters and equality checks.

Part of ``catalog.facets`` package (audit P3-3).
"""

from __future__ import annotations

import re

from catalog.facets.aux import _looks_like_aux_value, normalize_aux_switch_value
from catalog.facets.temp_sensor import (
    _looks_like_temp_sensor_value,
    normalize_temp_sensor_value,
)

# Marketing notes in Tilda EAV, e.g. «0,3 м² (для огнезадерживающих клапанов НО)».
_FACET_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*")
# Datasheet inequalities («< 0,5», «≤0,3 м²») → plain number for «до N».
_AREA_COMPARE_RE = re.compile(r"(?:<=|>=|≤|≥|<|>)")
_AREA_VALUE_RE = re.compile(
    r"^(до\s+)?(\d+(?:[.,]\d+)?)\s*(?:м²|m²|м2|m2)?\s*$",
    re.IGNORECASE,
)


def strip_facet_parenthetical(value: str) -> str:
    """Drop parenthetical marketing notes from a facet value."""
    cleaned = _FACET_PARENTHETICAL_RE.sub(" ", value)
    return " ".join(cleaned.split())


def normalize_area_attribute_value(value: str) -> str:
    """Canonical damper-area label: always ``до N м²``.

    Exact Tilda values (``0,5 м²``), inequalities (``< 0,5 м²``), and
    ``до 0,5`` collapse to the same chip so the facet stays uniform —
    never ``>``, ``<``, ``≥``, or ``≤`` in the label.

    Examples:
        ``до 0,5`` → ``до 0,5 м²``;
        ``< 0,5 м²`` → ``до 0,5 м²``;
        ``0,5 м²`` → ``до 0,5 м²``;
        ``3, 2 м²`` → ``до 3,2 м²``.

    Args:
        value: Raw EAV / facet value.

    Returns:
        Normalized area string with ``до`` and ``м²``.
    """
    raw = strip_facet_parenthetical(" ".join(str(value).strip().split()))
    if not raw:
        return raw
    # Tilda typo: «3, 2 м²» → «3,2 м²».
    raw = re.sub(r"(\d),\s+(\d)", r"\1,\2", raw)
    raw = " ".join(_AREA_COMPARE_RE.sub(" ", raw).split())
    match = _AREA_VALUE_RE.match(raw)
    if not match:
        # Keep unknown forms but unify unit spelling; still prefer «до».
        cleaned = raw.replace("m²", "м²").replace("м2", "м²").replace("m2", "м²")
        if cleaned.casefold().startswith("до "):
            return cleaned
        return f"до {cleaned}"
    number = match.group(2).replace(".", ",")
    # Merge «1» / «1,0» chips; datasheets use one decimal place.
    if re.fullmatch(r"\d+", number):
        number = f"{number},0"
    return f"до {number} м²"


def _looks_like_area_value(value: str) -> bool:
    """True if text looks like a damper-area facet value."""
    raw = strip_facet_parenthetical(" ".join((value or "").split()))
    if not raw:
        return False
    raw = re.sub(r"(\d),\s+(\d)", r"\1,\2", raw)
    raw = " ".join(_AREA_COMPARE_RE.sub(" ", raw).split())
    if _AREA_VALUE_RE.match(raw):
        return True
    return bool(re.search(r"м²|m²|м2|m2", raw, re.I))


def normalize_facet_value(
    facet_key: str,
    value: str,
    *,
    sku_code: str | None = None,
    description: str | None = None,
    category_slug: str | None = None,
) -> str:
    """Canonical chip label for aggregation.

    Area / voltage / aux / control collapse to canons.
    """
    val = " ".join(str(value).strip().split())
    if not val:
        return val
    if facet_key == "area":
        return normalize_area_attribute_value(val)
    if facet_key == "voltage":
        from catalog.etl.tech_copy import normalize_voltage_attribute_value

        return normalize_voltage_attribute_value(val, sku_code=sku_code)
    if facet_key == "control":
        from catalog.etl.tech_copy import normalize_control_attribute_value

        return normalize_control_attribute_value(
            val,
            sku_code=sku_code,
            category_slug=category_slug,
        )
    if facet_key == "aux_switch":
        return normalize_aux_switch_value(
            val,
            sku_code=sku_code,
            description=description or "",
        )
    if facet_key == "temp_sensor":
        return normalize_temp_sensor_value(val, sku_code=sku_code)
    return val


def values_match(stored: str, requested: str) -> bool:
    """Loose equality for facet values (``10`` ≈ ``10 Нм``)."""
    a = " ".join(stored.strip().casefold().split())
    b = " ".join(requested.strip().casefold().split())
    if not a or not b:
        return False
    # Area: «до 0,5» ≈ «до 0,5 м²»; strip parenthetical notes.
    if _looks_like_area_value(stored) or _looks_like_area_value(requested):
        if normalize_area_attribute_value(stored) == normalize_area_attribute_value(
            requested,
        ):
            return True
    if a == b:
        return True
    # Voltage: all Tilda spellings → same Belimo family.
    from catalog.etl.tech_copy import (
        detect_voltage_family,
        normalize_voltage_attribute_value,
    )

    if normalize_voltage_attribute_value(stored) == normalize_voltage_attribute_value(
        requested,
    ):
        # Only treat as voltage match when at least one side looks like voltage.
        if detect_voltage_family(stored) or detect_voltage_family(requested):
            return True
    # Aux: Да/Нет/1 SPDT ↔ Нет / SPDT-1 / SPDT-2 (without SKU context).
    # Thermal: «Без датчика» / SAF72… ↔ Нет / SAF72 (both sides must look thermal
    # so aux «Нет» vs «SPDT-1» does not enter this branch).
    if _looks_like_temp_sensor_value(stored) and _looks_like_temp_sensor_value(requested):
        return normalize_temp_sensor_value(stored) == normalize_temp_sensor_value(
            requested,
        )
    if _looks_like_aux_value(stored) or _looks_like_aux_value(requested):
        if normalize_aux_switch_value(stored) == normalize_aux_switch_value(requested):
            return True
    # Control: legacy «Пропорциональное (модулирующее)» ↔ «Пропорциональное».
    from catalog.etl.tech_copy import normalize_control_attribute_value

    if normalize_control_attribute_value(stored) == normalize_control_attribute_value(
        requested,
    ):
        low_join = f"{a} {b}"
        if re.search(r"управл|позицион|пропорциональн|открыто|модулир|плавн", low_join):
            return True
    # Numeric core: "10" matches "10 Нм", "24" matches "24 В"
    a_num = a.split()[0].replace(",", ".")
    b_num = b.split()[0].replace(",", ".")
    if a_num == b_num and a_num.replace(".", "", 1).isdigit():
        return True
    return a.startswith(b) or b.startswith(a)
