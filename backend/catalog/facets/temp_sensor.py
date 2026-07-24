"""Thermal sensor (SAF72) facet value helpers."""

from __future__ import annotations

import re

from catalog.etl.sku_variant import sku_code_is_thermal

TEMP_SENSOR_NONE = "Нет"
TEMP_SENSOR_SAF72 = "SAF72"

_NONE = frozenset(
    {
        "нет",
        "no",
        "none",
        "false",
        "0",
        "-",
        "—",
        "–",
        "без",
        "без датчика",
        "отсутствует",
    },
)


def normalize_temp_sensor_value(
    value: str,
    *,
    sku_code: str | None = None,
) -> str:
    """Canonical thermal facet / ТТХ: ``Нет`` / ``SAF72``.

    Args:
        value: Raw EAV (``Без датчика`` / ``SAF72 (…72 °C…)`` / ``Нет``).
        sku_code: Edition code; ``…DST`` / ``…ST-…F`` → SAF72 when text is empty.

    Returns:
        One of the two canonical labels.
    """
    raw = " ".join((value or "").split())
    low = raw.casefold()

    if "saf72" in low or re.search(r"\bsaf\b", low):
        return TEMP_SENSOR_SAF72
    if "72" in low and ("термо" in low or "датчик" in low or "ts1" in low):
        return TEMP_SENSOR_SAF72
    if low in _NONE or low.startswith("без датчик"):
        return TEMP_SENSOR_NONE
    if not raw and sku_code is not None:
        return TEMP_SENSOR_SAF72 if sku_code_is_thermal(sku_code) else TEMP_SENSOR_NONE
    if sku_code is not None and sku_code_is_thermal(sku_code):
        # Prefer edition when EAV is a vague «да» / marketing note.
        if low in {"да", "yes", "true", "1", "есть"}:
            return TEMP_SENSOR_SAF72
    if low in {"да", "yes", "true", "1", "есть"}:
        return TEMP_SENSOR_SAF72
    return TEMP_SENSOR_NONE if not raw else raw


def _looks_like_temp_sensor_value(value: str) -> bool:
    """True if text is a thermal-sensor facet label."""
    low = " ".join((value or "").casefold().split())
    if not low:
        return False
    if low in _NONE or low.startswith("без датчик"):
        return True
    if "saf72" in low or re.search(r"\bsaf\b", low):
        return True
    if "термодатчик" in low or "датчик температур" in low:
        return True
    return low in {"да", "yes", "нет", "no"}
