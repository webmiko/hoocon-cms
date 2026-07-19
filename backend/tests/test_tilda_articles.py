"""Tests for Tilda articles ETL helpers."""

from __future__ import annotations

from content.etl.tilda_articles import (
    clean_article_html,
    parse_published_at,
    rewrite_image_urls,
    slug_from_tilda_url,
    strip_html_to_text,
)


def test_slug_from_tilda_url() -> None:
    """Canonical slug is the last /tpost/ segment."""
    assert (
        slug_from_tilda_url(
            "https://hoocon.ru/statyi/tpost/4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov",
        )
        == "4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov"
    )


def test_strip_html_to_text() -> None:
    """Excerpt drops tags and collapses whitespace."""
    assert strip_html_to_text("<p>ООО <strong>Хогон</strong></p>") == "ООО Хогон"


def test_clean_article_html_strips_redactor_wrappers() -> None:
    """Tilda redactor wrappers are removed; content kept."""
    raw = (
        '<div class="t-redactor__tte-view">'
        '<h2 class="t-redactor__h2">Заголовок</h2>'
        '<div class="t-redactor__text">Текст</div>'
        "</div>"
    )
    out = clean_article_html(raw)
    assert "t-redactor__tte-view" not in out
    assert "Заголовок" in out
    assert "Текст" in out


def test_parse_published_at_moscow() -> None:
    """Published timestamps are Europe/Moscow-aware."""
    dt = parse_published_at("2025-07-01 12:18:01")
    assert dt is not None
    assert str(dt.tzinfo) == "Europe/Moscow"
    assert dt.year == 2025 and dt.month == 7 and dt.day == 1


def test_rewrite_image_urls() -> None:
    """Remote cover URLs in HTML are swapped to local media paths."""
    html = '<img src="https://static.tildacdn.com/x/a.jpg" alt="a">'
    out = rewrite_image_urls(
        html,
        {"https://static.tildacdn.com/x/a.jpg": "/media/article_covers/a.webp"},
    )
    assert "/media/article_covers/a.webp" in out
    assert "tildacdn" not in out
