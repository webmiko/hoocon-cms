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
    """PDP title starts with article code; omits Нм (shown in highlights)."""
    partial = sku_meta_title_partial("DA8MQU230-A", moment="8 Нм", voltage="230 В")
    assert partial.startswith("DA8MQU230-A")
    assert "Нм" not in partial
    assert "230 В" in partial
    full = format_branded_title(partial)
    assert len(full) <= TITLE_MAX_LEN
    assert "Нет" not in full


def test_sku_meta_title_shortens_long_voltage_canon() -> None:
    """Long Belimo voltage canon collapses to ``24 В`` in the title."""
    partial = sku_meta_title_partial(
        "DA5FU24-DS",
        moment="5 Нм",
        voltage="AC/DC 24 В, 50/60 Гц",
    )
    assert partial == "DA5FU24-DS — 24 В"
    assert "Нм" not in partial


def test_sku_meta_description_capped() -> None:
    """Description stays within 160 characters."""
    desc = sku_meta_description(
        "DA8MQU230-A",
        category_name="Электроприводы воздушные ускоренного срабатывания без пружины",
    )
    assert len(desc) <= 160
    assert "DA8MQU230-A" in desc


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
    )
    assert partial.startswith("DA8-X — ")
    assert "400" in partial or "AC" in partial


def test_sku_meta_description_without_category() -> None:
    """Fallback body when category is missing."""
    desc = sku_meta_description("DA8MQU230-A")
    assert "DA8MQU230-A" in desc
    assert "электропривод вентиляции" in desc
    assert len(desc) <= 160
