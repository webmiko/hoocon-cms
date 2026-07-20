"""Tests for social announcement compose + publishers (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
def test_compose_article_announcement_includes_title_and_url() -> None:
    """Announcement text has title, excerpt and absolute public URL."""
    from content.models import Article
    from social.compose import compose_announcement

    article = Article.objects.create(
        title="Приводы HVA: как выбрать момент",
        slug="privody-hva-kak-vybrat",
        excerpt="Краткий гайд для инженера.",
        is_published=True,
    )
    text = compose_announcement(article)
    assert "Приводы HVA" in text
    assert "Краткий гайд" in text
    assert "/statyi/privody-hva-kak-vybrat" in text


@pytest.mark.django_db
def test_compose_news_announcement_uses_novosti_path() -> None:
    """News announcements use /novosti/<slug> URL."""
    from content.models import News
    from social.compose import compose_announcement

    news = News.objects.create(
        title="Новая серия SA3",
        slug="novaya-seriya-sa3",
        is_published=True,
    )
    text = compose_announcement(news)
    assert "/novosti/novaya-seriya-sa3" in text


@pytest.mark.django_db
def test_announce_skips_when_channels_disabled() -> None:
    """No SocialPost rows when all channels are disabled."""
    from content.models import Article
    from sitesettings.models import SiteSettings
    from social.models import SocialPost
    from social.services import announce_content

    SiteSettings.load()
    article = Article.objects.create(
        title="Тест",
        slug="test-skip",
        is_published=True,
    )
    created = announce_content(article)
    assert created == []
    assert SocialPost.objects.count() == 0


@pytest.mark.django_db
def test_announce_telegram_creates_sent_post(settings) -> None:
    """Enabled Telegram channel creates a sent SocialPost via Bot API."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token-test"
    from content.models import Article
    from sitesettings.models import SiteSettings
    from social.models import SocialChannel, SocialPost, SocialPostStatus
    from social.services import announce_content

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_chat_id = "-100999"
    site.save()

    article = Article.objects.create(
        title="Анонс TG",
        slug="anons-tg",
        is_published=True,
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":42}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("social.publishers.urlopen", return_value=mock_resp):
        created = announce_content(article, channels=[SocialChannel.TELEGRAM])

    assert len(created) == 1
    post = SocialPost.objects.get()
    assert post.channel == SocialChannel.TELEGRAM
    assert post.status == SocialPostStatus.SENT
    assert post.external_id == "42"


@pytest.mark.django_db
def test_announce_is_idempotent_without_force(settings) -> None:
    """Second announce without force does not duplicate a successful post."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token-test"
    from content.models import Article
    from sitesettings.models import SiteSettings
    from social.models import SocialChannel, SocialPost, SocialPostStatus
    from social.services import announce_content

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_chat_id = "-100999"
    site.save()
    article = Article.objects.create(title="Once", slug="once", is_published=True)

    SocialPost.objects.create(
        content_type=SocialPost.content_type_for(article),
        object_id=article.pk,
        channel=SocialChannel.TELEGRAM,
        status=SocialPostStatus.SENT,
        message_preview="x",
    )
    created = announce_content(article, channels=[SocialChannel.TELEGRAM])
    assert created == []
    assert SocialPost.objects.count() == 1


@pytest.mark.django_db
def test_telegram_token_prefers_admin_over_env(settings) -> None:
    """SiteSettings.telegram_bot_token wins over TELEGRAM_BOT_TOKEN env."""
    settings.TELEGRAM_BOT_TOKEN = "env-token"
    from sitesettings.credentials import telegram_bot_token
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_bot_token = "admin-token"
    site.save()
    assert telegram_bot_token(site) == "admin-token"

    site.telegram_bot_token = ""
    site.save()
    assert telegram_bot_token(site) == "env-token"


@pytest.mark.django_db
def test_announce_uses_admin_telegram_token_without_env(settings) -> None:
    """Announce works when token is only in Admin (env empty)."""
    settings.TELEGRAM_BOT_TOKEN = ""
    from content.models import Article
    from sitesettings.models import SiteSettings
    from social.models import SocialChannel, SocialPostStatus
    from social.services import announce_content

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_chat_id = "-100999"
    site.telegram_bot_token = "admin-only-token"
    site.save()
    article = Article.objects.create(
        title="Admin token",
        slug="admin-token",
        is_published=True,
    )
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":7}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False
    with patch("social.publishers.urlopen", return_value=mock_resp):
        created = announce_content(article, channels=[SocialChannel.TELEGRAM])
    assert len(created) == 1
    assert created[0].status == SocialPostStatus.SENT


@pytest.mark.django_db
def test_site_settings_admin_blank_token_keeps_existing(django_user_model) -> None:
    """Saving Admin form with empty password field keeps stored token."""
    from django.test import Client

    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_bot_token = "keep-me"
    site.save()
    admin = django_user_model.objects.create_superuser(
        username="integ-admin",
        email="integ@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin)
    response = client.post(
        f"/admin/sitesettings/sitesettings/{site.pk}/change/",
        {
            "show_prices_on_site": "",
            "yandex_metrika_id": "",
            "ga4_measurement_id": "",
            "social_announce_on_publish": "",
            "telegram_enabled": "on",
            "telegram_bot_token": "",
            "telegram_chat_id": "-1001",
            "vk_enabled": "",
            "vk_access_token": "",
            "vk_group_id": "",
            "max_enabled": "",
            "max_bot_token": "",
            "max_chat_id": "",
            "_save": "Save",
        },
    )
    assert response.status_code in {200, 302}
    site.refresh_from_db()
    assert site.telegram_bot_token == "keep-me"
    assert site.telegram_chat_id == "-1001"
