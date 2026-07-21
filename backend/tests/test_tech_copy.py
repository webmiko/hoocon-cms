"""Tests for Belimo RU tech-copy normalization."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from catalog.etl.tech_copy import normalize_control_attribute_value, normalize_tech_copy
from catalog.management.commands.normalize_tech_copy import sku_category_slug


def test_sku_category_slug_guards_missing_product_or_category() -> None:
    """Do not read ``.slug`` when product or category FK is missing."""
    assert sku_category_slug(None) is None

    sku_no_product = MagicMock()
    sku_no_product.product_id = None
    assert sku_category_slug(sku_no_product) is None

    product = SimpleNamespace(category_id=None, category=None)
    sku_no_category = MagicMock()
    sku_no_category.product_id = 1
    sku_no_category.product = product
    assert sku_category_slug(sku_no_category) is None

    category = SimpleNamespace(slug="elektroprivody-vozdushnye")
    product_ok = SimpleNamespace(category_id=2, category=category)
    sku_ok = MagicMock()
    sku_ok.product_id = 1
    sku_ok.product = product_ok
    assert sku_category_slug(sku_ok) == "elektroprivody-vozdushnye"


def test_normalize_modulating_signal_drops_factory_dup() -> None:
    """Card form: no factory 0...10 dup; мА marked спецзаказ."""
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        normalize_modulating_signal_value,
    )

    long = "0(2)...10 В= / 0(4)...20 мА (Заводская установка 0...10 В=)"
    assert normalize_modulating_signal_value(long) == CONTROL_SIGNAL_Y_CANON
    assert "Заводская" not in normalize_modulating_signal_value(long)
    assert "спецзаказ" in CONTROL_SIGNAL_Y_CANON
    assert normalize_modulating_signal_value(CONTROL_SIGNAL_Y_CANON) == (CONTROL_SIGNAL_Y_CANON)
    assert normalize_modulating_signal_value("") == CONTROL_SIGNAL_Y_CANON
    assert normalize_modulating_signal_value("0(2)...10 В= / 0(4)...20 мА") == CONTROL_SIGNAL_Y_CANON
    # Voltage-only snippet: strip note if present, do not invent current range.
    assert (
        normalize_modulating_signal_value(
            "0(2)...10 В= (Заводская установка 0...10 В=)",
        )
        == "0(2)...10 В="
    )


def test_normalize_smooth_control_phrase() -> None:
    """«Плавное управление» → пропорциональное (модулирующее)."""
    assert (
        "пропорциональное (модулирующее) управление"
        in normalize_tech_copy(
            "Тип: Плавное управление - Нет",
        ).casefold()
    )
    assert "плавн" not in normalize_tech_copy("Плавное управление").casefold()


def test_normalize_on_off_and_signals() -> None:
    """Открыто/Закрыто kept; VDC, mA, класс защиты IP."""
    text = normalize_tech_copy(
        "Управление: Открыто/Закрыто. Сигнал 0(2)…10VDC/0(4)…20mA. Класс защиты IP54.",
    )
    assert "открыто/закрыто" in text.casefold()
    assert "В=" in text
    assert "мА" in text
    assert "VDC" not in text
    assert "степень защиты корпуса" in text.casefold()
    assert "класс защиты ip" not in text.casefold()


def test_normalize_damper_wording() -> None:
    """привод вентиляции → привод заслонки (со склонением)."""
    out = normalize_tech_copy("Список аналогов для привода вентиляции Hoocon")
    assert "привода заслонки" in out.casefold()
    assert "вентиляции" not in out.casefold()


def test_control_attribute_three_families() -> None:
    """EAV «Управление»: открыто/закрыто · 2-/3 · пропорциональное."""
    from catalog.etl.tech_copy import (
        CONTROL_FLOATING,
        CONTROL_MODULATING,
        CONTROL_ON_OFF,
    )

    assert normalize_control_attribute_value("Плавное управление") == CONTROL_MODULATING
    assert normalize_control_attribute_value("Пропорциональное (модулирующее)") == CONTROL_MODULATING
    assert normalize_control_attribute_value("Открыто/Закрыто") == CONTROL_ON_OFF
    assert normalize_control_attribute_value("2/3-позиционный") == CONTROL_FLOATING
    assert (
        normalize_control_attribute_value(
            "2-/3-позиционное",
            sku_code="da2mu24-d",
            category_slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
        )
        == CONTROL_FLOATING
    )
    assert (
        normalize_control_attribute_value(
            "2-/3-позиционное",
            sku_code="da5fu24-d",
            category_slug="elektroprivody-s-pruzhinnym-vozvratom",
        )
        == CONTROL_ON_OFF
    )
    assert (
        normalize_control_attribute_value(
            "2-/3-позиционное",
            sku_code="HVD24-5",
        )
        == CONTROL_ON_OFF
    )
    assert (
        normalize_control_attribute_value(
            "2-/3-позиционное",
            sku_code="sa3fu24-ds",
        )
        == CONTROL_ON_OFF
    )


def test_normalize_voltage_attribute_value() -> None:
    """All Tilda voltage spellings collapse to Belimo forms."""
    from catalog.etl.tech_copy import (
        VOLTAGE_24_CANON,
        VOLTAGE_230_CANON,
        normalize_voltage_attribute_value,
    )

    assert normalize_voltage_attribute_value("24 В") == VOLTAGE_24_CANON
    assert normalize_voltage_attribute_value("AC/DC 24V 50/60 Гц") == VOLTAGE_24_CANON
    assert (
        normalize_voltage_attribute_value(
            "AC/DC 24 В (диапазон 19.2−28.8 В)",
        )
        == VOLTAGE_24_CANON
    )
    assert normalize_voltage_attribute_value("230 В") == VOLTAGE_230_CANON
    assert normalize_voltage_attribute_value("AC 100−240V 50/60 Гц") == VOLTAGE_230_CANON
    assert (
        normalize_voltage_attribute_value(
            "AC/DC 24 В (диапазон 19.2−28.8 В)",
            sku_code="sa3fu230-ds",
        )
        == VOLTAGE_230_CANON
    )


def test_normalize_running_time_value() -> None:
    """Belimo RU: сек → с; display unit omitted when already in value."""
    from catalog.etl.tech_copy import (
        attribute_display_unit,
        normalize_running_time_value,
    )

    assert normalize_running_time_value("≤ 100 сек") == "≤ 100 с"
    assert normalize_running_time_value("≤ 30 секунд (90°)") == "≤ 30 с (90°)"
    assert normalize_running_time_value("≤ 60 с (90°)") == "≤ 60 с (90°)"
    assert attribute_display_unit("≤ 100 с", "с") == ""
    assert attribute_display_unit("≤ 100 сек", "с") == ""
    assert attribute_display_unit("100", "с") == "с"
