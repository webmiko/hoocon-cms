"""SERP title/description length helpers (Google + Yandex)."""

from __future__ import annotations

from config.seo.meta_text import (
    TITLE_MAX_LEN,
    format_branded_title,
    format_meta_description,
    sku_meta_description,
    sku_meta_title_partial,
)
from config.seo.routes import DEFAULT_DESCRIPTION, SITE_NAME


def test_branded_title_within_snippet_limit() -> None:
    """Full title with brand stays within 60 characters."""
    long = "Очень длинный заголовок статьи про электроприводы ОВК и заслонки"
    title = format_branded_title(long)
    assert len(title) <= TITLE_MAX_LEN
    assert SITE_NAME in title


def test_sku_meta_title_puts_code_first() -> None:
    """PDP title keeps the code and the torque so neighbouring cards differ in the SERP."""
    partial = sku_meta_title_partial(
        "DA8MQU230-A",
        moment="8 Нм",
        voltage="230 В",
        analog="SM230A",
        kind="привод",
    )
    assert partial == "DA8MQU230-A привод 8 Нм 230 В, аналог SM230A"
    full = format_branded_title(partial)
    assert len(full) <= TITLE_MAX_LEN
    assert "Нет" not in full


def test_sku_meta_title_shortens_long_voltage_canon() -> None:
    """Long Belimo voltage canon collapses to ``24 В`` and the torque stays."""
    partial = sku_meta_title_partial(
        "DA5FU24-DS",
        moment="5 Нм",
        voltage="AC/DC 24 В, 50/60 Гц",
        analog="LF24",
        kind="привод",
    )
    assert partial == "DA5FU24-DS привод 5 Нм 24 В, аналог LF24"


def test_sku_meta_description_capped() -> None:
    """Description stays within 160 characters and keeps torque and the Belimo code."""
    desc = sku_meta_description(
        "DA8MQU230-A",
        category_name="Электроприводы воздушные ускоренного срабатывания без пружины",
        moment="8 Нм",
        voltage="AC 100…240 В",
        analog="SM230A-SR",
    )
    assert len(desc) <= 160
    assert "DA8MQU230-A" in desc
    assert "8 Нм" in desc
    assert "SM230A-SR" in desc


def test_default_description_within_limit() -> None:
    """Home fallback description fits snippet."""
    assert len(DEFAULT_DESCRIPTION) <= 160
    assert len(format_meta_description(DEFAULT_DESCRIPTION)) <= 160


def test_branded_title_none_uses_default() -> None:
    """Empty partial falls back to DEFAULT_TITLE."""
    title = format_branded_title(None)
    assert len(title) <= TITLE_MAX_LEN
    assert title


def test_branded_title_keeps_existing_brand() -> None:
    """Partial that already contains SITE_NAME is not double-suffixed."""
    partial = f"Каталог {SITE_NAME}"
    title = format_branded_title(partial)
    assert title.count(SITE_NAME) == 1
    assert len(title) <= TITLE_MAX_LEN


def test_sku_meta_title_unknown_long_voltage() -> None:
    """Unknown long voltage string is compacted without inventing 24/230."""
    partial = sku_meta_title_partial(
        "DA8-X",
        voltage="AC 400 В трёхфазный нестандарт",
        kind="привод",
    )
    assert partial.startswith("DA8-X привод ")
    assert "400" in partial or "AC" in partial


def test_sku_meta_descriptions_differ_by_torque() -> None:
    """Two cards in one category must not share a description tail."""
    left = sku_meta_description("H8101-A", category_name="Комплекты", moment="5 Нм", voltage="24 В")
    right = sku_meta_description("H8101-B", category_name="Комплекты", moment="10 Нм", voltage="230 В")
    assert left != right
    assert "5 Нм" in left
    assert "10 Нм" in right


def test_sku_meta_description_without_category() -> None:
    """Fallback body when category is missing."""
    desc = sku_meta_description("DA8MQU230-A")
    assert "DA8MQU230-A" in desc
    assert "электропривод вентиляции" in desc
    assert len(desc) <= 160
