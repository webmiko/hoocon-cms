"""Coverage tests for thermal-sensor facet helpers."""

from __future__ import annotations

import pytest

from catalog.facets.temp_sensor import (
    TEMP_SENSOR_NONE,
    TEMP_SENSOR_SAF72,
    _looks_like_temp_sensor_value,
    normalize_temp_sensor_value,
)


@pytest.mark.parametrize(
    ("raw", "sku_code", "expected"),
    [
        ("SAF72 (термодатчик)", None, TEMP_SENSOR_SAF72),
        ("72 °C термодатчик", None, TEMP_SENSOR_SAF72),
        ("TS1…72", None, TEMP_SENSOR_SAF72),
        ("Без датчика", None, TEMP_SENSOR_NONE),
        ("нет", None, TEMP_SENSOR_NONE),
        ("", "SA5MU-DST", TEMP_SENSOR_SAF72),
        ("", "SA5MU", TEMP_SENSOR_NONE),
        ("да", "SA5MU-DST", TEMP_SENSOR_SAF72),
        ("yes", None, TEMP_SENSOR_SAF72),
        ("кастомная метка", None, "кастомная метка"),
        ("", None, TEMP_SENSOR_NONE),
    ],
)
def test_normalize_temp_sensor_value(
    raw: str,
    sku_code: str | None,
    expected: str,
) -> None:
    """Canonical labels for empty / vague / SAF72 / none EAV values."""
    assert normalize_temp_sensor_value(raw, sku_code=sku_code) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", False),
        ("термодатчик SAF72", True),
        ("датчик температуры", True),
        ("без датчика", True),
        ("да", True),
        ("момент 5 Нм", False),
    ],
)
def test_looks_like_temp_sensor_value(raw: str, expected: bool) -> None:
    """Heuristic for thermal facet labels."""
    assert _looks_like_temp_sensor_value(raw) is expected
