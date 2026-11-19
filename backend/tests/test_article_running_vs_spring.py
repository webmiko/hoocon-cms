"""Article on motor time vs spring return quotes the RU manuals, not a rule of thumb."""

from __future__ import annotations

from pathlib import Path

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "content" / "fixtures" / "article_vremya_povorota_i_vozvrat_pruzhiny.html"
)

# Upper bounds from RU manual page 2, written into the article as text.
_MANUAL_BOUNDS = (
    "DA5FU-D_DS",
    "&lt; 70 с",
    "&lt; 20 с",
    "DA5FU24-A_AS",
    "&lt; 100 с",
    "DA10FU-D_DS",
    "&lt; 150 с",
    "&lt; 25 с",
    "SA7MU-DS",
    "&lt; 30 с",
    "SA10MU-DS",
    "&lt; 45 с",
)


def test_running_vs_spring_covers_exist() -> None:
    """Light and dark WebP covers sit next to the article fixture."""
    root = _FIXTURE.parent
    assert (root / "article_vremya_povorota_i_vozvrat_pruzhiny_cover.webp").is_file()
    assert (root / "article_vremya_povorota_i_vozvrat_pruzhiny_cover_dark.webp").is_file()


def test_running_vs_spring_article_quotes_manual_page_two() -> None:
    """DA5FU on/off is &lt; 70 s motor and &lt; 20 s spring; SA7MU has no spring line."""
    html = _FIXTURE.read_text(encoding="utf-8")
    for needle in _MANUAL_BOUNDS:
        assert needle in html
    assert "8 Нм" not in html
    assert "стр. 2" in html or "страницы 2" in html


def test_running_vs_spring_article_is_scheduled_and_announced() -> None:
    """Seed and the go-live beat both know the new guide."""
    from content.article_go_live import AUTO_GO_LIVE_NEWS_SLUGS
    from content.management.commands.seed_site_content import (
        ARTICLE_BODIES,
        ARTICLE_EXCERPTS,
        ARTICLE_TITLES,
        _article_publish_schedule,
    )

    slug = "vremya-povorota-i-vozvrat-pruzhiny"
    assert slug in ARTICLE_BODIES
    assert slug in ARTICLE_EXCERPTS
    assert slug in ARTICLE_TITLES
    assert slug in AUTO_GO_LIVE_NEWS_SLUGS
    published = _article_publish_schedule()[slug]
    assert published.year == 2026 and published.month == 11 and published.day == 20
    assert published.hour == 9 and str(published.tzinfo) == "Europe/Moscow"
