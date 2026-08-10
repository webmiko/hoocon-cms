"""Tests for DA..MU series copy helpers."""

from __future__ import annotations

from catalog.etl.series_copy_damu import instructions_for_damu_sku


def test_instructions_for_damu_sku_scopes_voltage_and_aux() -> None:
    """24 В -D omits 230 В and auxiliary-switch chapter."""
    text = instructions_for_damu_sku("DA4MU24-D")
    assert text is not None
    assert "Hoocon DA4MU" in text
    assert "AC/DC 24 В" in text
    assert "100…240" not in text
    assert "Исполнения 230" not in text
    assert "Вспомогательные переключатели" not in text
    assert "84,8 × 145,6 × 65" in text
    assert "8…16 мм" in text


def test_instructions_for_damu_sku_modulating_with_aux() -> None:
    """230 В -AS keeps proportional + aux chapters only for that edition."""
    text = instructions_for_damu_sku("DA4MU230-AS")
    assert text is not None
    assert "AC 100…240 В" in text
    assert "AC/DC 24 В" not in text
    assert "Пропорциональное управление" in text
    assert "Вспомогательные переключатели" in text
    assert "клеммы 21,22" in text
    assert "Переключатель b" in text
    assert "DIP-переключатели" in text
    assert "Двухпозиционное управление" not in text
    assert "0(4)...20 мА (спецзаказ)" in text
    assert "по схеме в инструкции" not in text
    assert "по заводской таблице в инструкции" not in text


def test_instructions_for_damu_sku_on_off_aux_omits_dip() -> None:
    """-DS gets aux angle table without modulating DIP section."""
    text = instructions_for_damu_sku("DA2MU24-DS")
    assert text is not None
    assert "Вспомогательные переключатели" in text
    assert "клеммы 21,22" in text
    assert "Переключатель b" not in text
    assert "DIP-переключатели" not in text


def test_instructions_for_damu_sku_rejects_other_series() -> None:
    assert instructions_for_damu_sku("DA5FU24-D") is None
    assert instructions_for_damu_sku("") is None
