"""Unit tests for H81 kit DN-specific power / run-time bands."""

from __future__ import annotations

from catalog.etl.h81_kits import all_h81_kit_series


def _kit(code: str):
    return next(k for k in all_h81_kit_series() if k.code == code)


def test_h8101_power_by_dn() -> None:
    small = _kit("H8101-BV215A")
    large = _kit("H8101-BV250A")
    assert "DN15" not in small.power_consumption("24")
    assert small.power_consumption("24") == ("В рабочем режиме: 3 Вт / В режиме ожидания: 1 Вт")
    assert large.power_consumption("24") == ("В рабочем режиме: 4,5 Вт / В режиме ожидания: 1 Вт")


def test_h8102_power_by_dn() -> None:
    assert _kit("H8102-BV225A").power_consumption("230") == ("В рабочем режиме: 3,5 Вт / В режиме ожидания: 1 Вт")
    assert _kit("H8102-BV232A").power_consumption("230") == ("В рабочем режиме: 5 Вт / В режиме ожидания: 1 Вт")


def test_h8105_power_and_run_time_by_dn() -> None:
    dn20 = _kit("H8105-BV220A")
    dn32 = _kit("H8105-BV232A")
    dn50 = _kit("H8105-BV250A")
    assert dn20.power_consumption("24") == "В рабочем режиме: 3 Вт / ожидание: 0,8 Вт"
    assert dn32.power_consumption("24") == "В рабочем режиме: 3 Вт / ожидание: 0,8 Вт"
    assert dn50.power_consumption("24") == "В рабочем режиме: 4,5 Вт / ожидание: 1,0 Вт"
    assert dn20.run_time == "< 50 с"
    assert dn32.run_time == "< 70 с"
    assert dn50.run_time == "< 55 с"


def test_h8104_power_by_flanged_dn() -> None:
    assert _kit("H8104-BV265").power_consumption("24") == ("В рабочем режиме: 8 Вт / В режиме ожидания: 1 Вт")
    assert _kit("H8104-BV2100").power_consumption("24") == ("В рабочем режиме: 15 Вт / В режиме ожидания: 3 Вт")
