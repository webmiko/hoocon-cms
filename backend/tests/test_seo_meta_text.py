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
    """PDP title starts with article code and fits with brand."""
    partial = sku_meta_title_partial("DA8MQU230-A", moment="8 Нм", voltage="230 В")
    assert partial.startswith("DA8MQU230-A")
    full = format_branded_title(partial)
    assert len(full) <= TITLE_MAX_LEN
    assert "Нет" not in full


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
