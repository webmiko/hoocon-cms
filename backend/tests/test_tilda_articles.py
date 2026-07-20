"""Tests for Tilda articles ETL helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from content.etl.tilda_articles import (
    clean_article_html,
    collect_image_urls,
    download_bytes,
    fetch_feed_posts,
    fetch_post,
    parse_published_at,
    rewrite_image_urls,
    scrape_all_articles,
    scrape_article,
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
    assert slug_from_tilda_url("https://hoocon.ru/news/partner/foo") == "partner-foo"
    assert slug_from_tilda_url("https://hoocon.ru/novosti/bar") == "bar"


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
    assert parse_published_at("") is None
    assert parse_published_at("not-a-date") is None


def test_rewrite_image_urls() -> None:
    """Remote cover URLs in HTML are swapped to local media paths."""
    html = '<img src="https://static.tildacdn.com/x/a.jpg" alt="a">'
    out = rewrite_image_urls(
        html,
        {"https://static.tildacdn.com/x/a.jpg": "/media/article_covers/a.webp"},
    )
    assert "/media/article_covers/a.webp" in out
    assert "tildacdn" not in out
    assert rewrite_image_urls(html, {}) == html


def test_collect_image_urls_dedupes() -> None:
    html = '<img src="https://static.tildacdn.com/a.jpg"><img src="https://example.com/b.png">'
    urls = collect_image_urls(
        html,
        "https://static.tildacdn.com/a.jpg",
        "https://thb.tildacdn.com/c.jpg",
    )
    assert urls[0] == "https://static.tildacdn.com/a.jpg"
    assert "https://thb.tildacdn.com/c.jpg" in urls
    assert "https://example.com/b.png" in urls


def _mock_urlopen(payload: dict[str, object]) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_fetch_feed_posts_and_post() -> None:
    feed = {"posts": [{"uid": "1", "title": "A"}, "bad", {"uid": "2"}]}
    with patch(
        "content.etl.tilda_articles.urllib.request.urlopen",
        return_value=_mock_urlopen(feed),
    ):
        posts = fetch_feed_posts("feed-1")
    assert len(posts) == 2
    assert posts[0]["uid"] == "1"

    with patch(
        "content.etl.tilda_articles.urllib.request.urlopen",
        return_value=_mock_urlopen({"posts": "nope"}),
    ):
        assert fetch_feed_posts() == []

    with patch(
        "content.etl.tilda_articles.urllib.request.urlopen",
        return_value=_mock_urlopen(
            {
                "post": {
                    "uid": "9",
                    "url": "https://hoocon.ru/statyi/tpost/abc-title",
                    "title": "Hello",
                    "text": "<p>Body</p>",
                    "descr": "<p>Ex</p>",
                    "image": "https://static.tildacdn.com/c.jpg",
                    "published": "2025-01-02 10:00:00",
                },
            },
        ),
    ):
        post = fetch_post("9")
    assert post["title"] == "Hello"

    with patch(
        "content.etl.tilda_articles.urllib.request.urlopen",
        return_value=_mock_urlopen({"post": "x"}),
    ):
        with pytest.raises(ValueError, match="Missing post"):
            fetch_post("x")


def test_download_bytes() -> None:
    resp = MagicMock()
    resp.read.return_value = b"abc"
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    with patch(
        "content.etl.tilda_articles.urllib.request.urlopen",
        return_value=resp,
    ):
        assert download_bytes("https://example.com/x") == b"abc"


def test_scrape_article_and_all() -> None:
    stub = {
        "uid": "42",
        "url": "https://hoocon.ru/statyi/tpost/slug-one",
        "title": "T",
        "descr": "D",
    }
    full = {
        "url": "https://hoocon.ru/statyi/tpost/slug-one",
        "title": "Full title",
        "descr": "<p>Excerpt</p>",
        "text": '<div class="t-redactor__tte-view"><p>Body</p></div>',
        "image": "https://static.tildacdn.com/c.jpg",
        "published": "2025-03-04 15:00:00",
    }
    with patch(
        "content.etl.tilda_articles.fetch_post",
        return_value=full,
    ):
        art = scrape_article(stub)
    assert art.slug == "slug-one"
    assert art.title == "Full title"
    assert art.excerpt == "Excerpt"
    assert "Body" in art.body_html
    assert art.cover_url.endswith("c.jpg")
    assert art.published_at is not None

    with pytest.raises(ValueError, match="missing uid"):
        scrape_article({"title": "x"})

    with (
        patch(
            "content.etl.tilda_articles.fetch_feed_posts",
            return_value=[stub, {"uid": "bad"}],
        ),
        patch(
            "content.etl.tilda_articles.scrape_article",
            side_effect=[art, ValueError("boom")],
        ),
    ):
        all_arts = scrape_all_articles()
    assert len(all_arts) == 1
