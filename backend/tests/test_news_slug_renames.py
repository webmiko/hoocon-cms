"""Tests for news slug renames (Tilda ID → readable ЧПУ + 301 + cover folder)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from content.models import News
from content.news_slug_renames import (
    NEWS_SLUG_RENAMES,
    apply_news_slug_renames,
    canonical_news_slug,
    relocate_news_cover_to_slug,
)
from redirects.models import Redirect


@pytest.mark.django_db
def test_apply_news_slug_renames_renames_and_redirects() -> None:
    """Old Tilda-prefixed slug becomes canonical; 301 maps /novosti and /news."""
    old_slug = "4s6cri8961-aquatherm-2025"
    new_slug = NEWS_SLUG_RENAMES[old_slug]
    News.objects.create(
        title="Aquatherm 2025",
        slug=old_slug,
        body="<p>x</p>",
        is_published=True,
    )

    applied = apply_news_slug_renames()

    assert (old_slug, new_slug) in applied
    assert not News.objects.filter(slug=old_slug).exists()
    assert News.objects.filter(slug=new_slug).exists()
    for from_path in (f"/novosti/{old_slug}", f"/news/{old_slug}"):
        redir = Redirect.objects.get(from_path=from_path)
        assert redir.to_path == f"/novosti/{new_slug}"
        assert redir.status_code == 301
        assert redir.is_active is True


@pytest.mark.django_db
def test_apply_news_slug_renames_idempotent_when_already_canonical() -> None:
    """Second run keeps the canonical news and refreshes redirects."""
    new_slug = "aquatherm-2025"
    News.objects.create(
        title="Aquatherm 2025",
        slug=new_slug,
        body="<p>y</p>",
        is_published=True,
    )

    apply_news_slug_renames()
    apply_news_slug_renames()

    assert News.objects.filter(slug=new_slug).count() == 1
    assert Redirect.objects.filter(to_path=f"/novosti/{new_slug}").count() >= 1


@pytest.mark.django_db
def test_relocate_news_cover_to_canonical_slug_folder(
    tmp_path: Path,
    settings: pytest.SettingsWrapper,
) -> None:
    """Cover files leave Tilda-prefixed folders after slug is already canonical."""
    media = tmp_path / "media"
    media.mkdir()
    settings.MEDIA_ROOT = media

    from django.core.files.storage import default_storage

    old_folder = "4s6cri8961-aquatherm-2025"
    new_slug = "aquatherm-2025"
    news = News.objects.create(
        title="Aquatherm 2025",
        slug=new_slug,
        body="<p>x</p>",
        is_published=True,
    )
    old_name = f"news_covers/{old_folder}/cover.webp"
    default_storage.save(old_name, ContentFile(b"fake-webp-bytes"))
    news.cover.name = old_name
    news.save(update_fields=["cover", "updated_at"])
    assert old_folder in news.cover.name

    new_path = relocate_news_cover_to_slug(news)

    news.refresh_from_db()
    assert new_path is not None
    assert news.cover.name == f"news_covers/{new_slug}/cover.webp"
    assert (media / "news_covers" / new_slug / "cover.webp").is_file()
    assert not (media / "news_covers" / old_folder / "cover.webp").exists()


def test_canonical_news_slug_maps_tilda_prefix() -> None:
    assert canonical_news_slug("4s6cri8961-aquatherm-2025") == "aquatherm-2025"
    assert canonical_news_slug("hoocon-airvent-2026") == "hoocon-airvent-2026"
