"""Admin UI for manual social announce on Article / News."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_news_change_form_shows_mobile_social_announce_banner(
    client,
    django_user_model,
) -> None:
    """Published news: POST banner above form (phone path; no changelist checkboxes)."""
    from content.models import News

    admin = django_user_model.objects.create_superuser(
        username="news-announce-ui",
        email="news-announce@example.test",
        password="password12",
    )
    news = News.objects.create(
        title="Соцанонс UI",
        slug="social-announce-ui-test",
        body="<p>x</p>",
        is_published=True,
    )
    client.force_login(admin)
    html = client.get(reverse("admin:content_news_change", args=[news.pk])).content.decode()
    assert "hoocon-social-announce-banner" in html
    assert 'method="post"' in html
    assert "announce-social" in html
    assert "Опубликовать в соцсети" in html
    assert 'material-symbols-outlined">campaign' in html


@pytest.mark.django_db
def test_news_draft_hides_social_announce_controls(client, django_user_model) -> None:
    """Draft news must not show announce controls."""
    from content.models import News

    admin = django_user_model.objects.create_superuser(
        username="news-draft-ui",
        email="news-draft@example.test",
        password="password12",
    )
    news = News.objects.create(
        title="Черновик",
        slug="draft-no-social",
        body="b",
        is_published=False,
    )
    client.force_login(admin)
    html = client.get(reverse("admin:content_news_change", args=[news.pk])).content.decode()
    assert "hoocon-social-announce-banner" not in html
    assert "announce-social" not in html


@pytest.mark.django_db
def test_news_announce_social_post_triggers_service(client, django_user_model) -> None:
    """Banner/tool POST hits announce view and calls announce_content."""
    from content.models import News

    admin = django_user_model.objects.create_superuser(
        username="news-announce-post",
        email="news-post@example.test",
        password="password12",
    )
    news = News.objects.create(
        title="Пост",
        slug="post-social",
        body="<p>x</p>",
        is_published=True,
    )
    client.force_login(admin)
    url = reverse("admin:content_news_announce_social", args=[news.pk])
    with patch("social.admin.announce_content", return_value=[]) as mocked:
        response = client.post(url)
    assert response.status_code == 302
    mocked.assert_called_once()
    assert mocked.call_args.args[0].pk == news.pk
    assert mocked.call_args.kwargs.get("force") is True


def test_social_announce_banner_styles_in_loaded_extras_css() -> None:
    """Mobile banner uses rules from Unfold extras (loaded admin CSS)."""
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8"
    )
    assert ".hoocon-social-announce-form__btn" in css
    block = css.split("/* Article/News: mobile-friendly social announce", 1)[1].split(
        "/* Sticky header:",
        1,
    )[0]
    assert "@media (min-width: 768px)" in block
    assert ".hoocon-social-announce-banner" in block and "display: none" in block
