"""Tilda scrape commands keep CMS edits (M43).

Before: every rerun overwrote title/body edited in Admin, re-published
hidden posts, re-enabled disabled legacy redirects, and downloaded images
while holding the row transaction open.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import connection
from PIL import Image

from content.etl.tilda_articles import ScrapedArticle
from content.models import Article, News
from redirects.models import Redirect

ARTICLES = "content.management.commands.scrape_hoocon_articles"
NEWS = "content.management.commands.scrape_hoocon_news"


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, format="PNG")
    return buf.getvalue()


def _item(slug: str, *, title: str = "С Тильды", source_url: str = "") -> ScrapedArticle:
    return ScrapedArticle(
        uid="1",
        slug=slug,
        title=title,
        excerpt="Анонс",
        body_html="<p>Текст с Тильды</p>",
        cover_url="https://static.tildacdn.com/cover.png",
        published_at=None,
        source_url=source_url,
    )


@pytest.mark.django_db
def test_articles_rerun_keeps_admin_edit_and_hidden_state(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    Article.objects.create(slug="kak-vybrat", title="Правка редактора", body="<p>Наш текст</p>", is_published=False)
    with patch(f"{ARTICLES}.scrape_all_articles", return_value=[_item("kak-vybrat")]):
        call_command("scrape_hoocon_articles", "--skip-images")
    article = Article.objects.get(slug="kak-vybrat")
    assert article.title == "Правка редактора"
    assert article.body == "<p>Наш текст</p>"
    assert article.is_published is False


@pytest.mark.django_db
def test_articles_force_refreshes_text_but_not_publication(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    Article.objects.create(slug="kak-vybrat", title="Старое", body="<p>Старое</p>", is_published=False)
    with patch(f"{ARTICLES}.scrape_all_articles", return_value=[_item("kak-vybrat", title="Новое")]):
        call_command("scrape_hoocon_articles", "--skip-images", "--force")
    article = Article.objects.get(slug="kak-vybrat")
    assert article.title == "Новое"
    assert article.is_published is False


@pytest.mark.django_db
def test_articles_create_new_post_published(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    with (
        patch(f"{ARTICLES}.scrape_all_articles", return_value=[_item("novaya")]),
        patch("content.etl.scrape_import.download_bytes", return_value=_png()),
    ):
        call_command("scrape_hoocon_articles")
    article = Article.objects.get(slug="novaya")
    assert article.is_published is True
    assert article.cover.name.endswith(".webp")


@pytest.mark.django_db(transaction=True)
def test_images_are_downloaded_outside_db_transaction(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    in_atomic: list[bool] = []

    def _download(_url: str) -> bytes:
        in_atomic.append(connection.in_atomic_block)
        return _png()

    with (
        patch(f"{NEWS}.scrape_all_articles", return_value=[_item("vystavka")]),
        patch("content.etl.scrape_import.download_bytes", side_effect=_download),
    ):
        call_command("scrape_hoocon_news")
    assert in_atomic == [False]
    assert News.objects.get(slug="vystavka").cover


@pytest.mark.django_db
def test_news_rerun_keeps_disabled_legacy_redirect(settings, tmp_path) -> None:
    settings.MEDIA_ROOT = str(tmp_path)
    Redirect.objects.create(from_path="/news/old-post", to_path="/novosti/somewhere", is_active=False)
    item = _item("vystavka", source_url="https://hoocon.ru/news/old-post")
    with patch(f"{NEWS}.scrape_all_articles", return_value=[item]):
        call_command("scrape_hoocon_news", "--skip-images")
    redirect = Redirect.objects.get(from_path="/news/old-post")
    assert redirect.is_active is False
    assert redirect.to_path == "/novosti/somewhere"
