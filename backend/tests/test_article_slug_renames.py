"""Tests for article slug renames (Tilda ID → readable ЧПУ + 301)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from content.article_slug_renames import (
    ARTICLE_SLUG_RENAMES,
    apply_article_slug_renames,
    relocate_article_cover_to_slug,
)
from content.models import Article
from redirects.models import Redirect


@pytest.mark.django_db
def test_apply_article_slug_renames_renames_and_redirects() -> None:
    """Old Tilda-prefixed slug becomes canonical; 301 maps /statyi paths."""
    old_slug = "4uicugaoh1-spetsifikatsiya-modelnogo-ryada-privodov"
    new_slug = ARTICLE_SLUG_RENAMES[old_slug]
    Article.objects.create(
        title="Спецификация",
        slug=old_slug,
        body="<p>x</p>",
        is_published=True,
    )

    applied = apply_article_slug_renames()

    assert (old_slug, new_slug) in applied
    assert not Article.objects.filter(slug=old_slug).exists()
    assert Article.objects.filter(slug=new_slug).exists()
    redir = Redirect.objects.get(from_path=f"/statyi/{old_slug}")
    assert redir.to_path == f"/statyi/{new_slug}"
    assert redir.status_code == 301
    assert redir.is_active is True


@pytest.mark.django_db
def test_apply_application_article_slug_rename() -> None:
    """Application article drops Tilda prefix; 301 from old /statyi path."""
    old_slug = "2zbgj89cp1-primenenie-privodov-v-sistemah-ventilyat"
    new_slug = ARTICLE_SLUG_RENAMES[old_slug]
    Article.objects.create(
        title="Применение",
        slug=old_slug,
        body="<p>x</p>",
        is_published=True,
    )

    apply_article_slug_renames()

    assert not Article.objects.filter(slug=old_slug).exists()
    assert Article.objects.filter(slug=new_slug).exists()
    redir = Redirect.objects.get(from_path=f"/statyi/{old_slug}")
    assert redir.to_path == f"/statyi/{new_slug}"
    assert redir.status_code == 301


@pytest.mark.django_db
def test_apply_all_tilda_article_slug_renames() -> None:
    """Every mapped Tilda-prefixed slug gets a 301 to the canonical ЧПУ."""
    for old_slug, new_slug in ARTICLE_SLUG_RENAMES.items():
        if Article.objects.filter(slug=new_slug).exists():
            continue
        Article.objects.create(
            title=new_slug,
            slug=old_slug,
            body="<p>x</p>",
            is_published=True,
        )

    apply_article_slug_renames()

    for old_slug, new_slug in ARTICLE_SLUG_RENAMES.items():
        assert not Article.objects.filter(slug=old_slug).exists()
        assert Article.objects.filter(slug=new_slug).exists()
        redir = Redirect.objects.get(from_path=f"/statyi/{old_slug}")
        assert redir.to_path == f"/statyi/{new_slug}"
        assert redir.status_code == 301


@pytest.mark.django_db
def test_apply_article_slug_renames_idempotent_when_already_canonical() -> None:
    """Second run keeps the canonical article and refreshes the redirect."""
    new_slug = "spetsifikatsiya-modelnogo-ryada-privodov"
    Article.objects.create(
        title="Спецификация",
        slug=new_slug,
        body="<p>y</p>",
        is_published=True,
    )

    apply_article_slug_renames()
    apply_article_slug_renames()

    assert Article.objects.filter(slug=new_slug).count() == 1
    assert Redirect.objects.filter(to_path=f"/statyi/{new_slug}").count() >= 1


@pytest.mark.django_db
def test_relocate_article_cover_to_canonical_slug_folder(
    tmp_path: Path,
    settings: pytest.SettingsWrapper,
) -> None:
    """Cover files leave Tilda-prefixed folders after slug is already canonical."""
    media = tmp_path / "media"
    media.mkdir()
    settings.MEDIA_ROOT = media

    from django.core.files.storage import default_storage

    old_folder = "2zbgj89cp1-primenenie-privodov-v-sistemah-ventilyat"
    new_slug = "primenenie-privodov-v-sistemah-ventilyatsii"
    article = Article.objects.create(
        title="Применение",
        slug=new_slug,
        body="<p>x</p>",
        is_published=True,
    )
    # Bypass upload_to so the field still points at the legacy Tilda folder.
    old_name = f"article_covers/{old_folder}/cover.webp"
    default_storage.save(old_name, ContentFile(b"fake-webp-bytes"))
    article.cover.name = old_name
    article.save(update_fields=["cover", "updated_at"])
    assert old_folder in article.cover.name

    new_path = relocate_article_cover_to_slug(article)

    article.refresh_from_db()
    assert new_path is not None
    assert article.cover.name == f"article_covers/{new_slug}/cover.webp"
    assert (media / "article_covers" / new_slug / "cover.webp").is_file()
    assert not (media / "article_covers" / old_folder / "cover.webp").exists()
