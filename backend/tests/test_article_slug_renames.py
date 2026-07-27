"""Tests for article slug renames (Tilda ID → readable ЧПУ + 301)."""

from __future__ import annotations

import pytest

from content.article_slug_renames import (
    ARTICLE_SLUG_RENAMES,
    apply_article_slug_renames,
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
