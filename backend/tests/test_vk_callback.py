"""Tests for VK Callback API (community messages → support chat)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

from social.publishers import PublishResult
from social.vk_bot import handle_vk_callback, vk_community_write_link


def _message_new_event(*, user_id: int, text: str, message_id: int = 1001) -> dict:
    return {
        "type": "message_new",
        "group_id": 242719752,
        "secret": "expected-secret",
        "object": {
            "message": {
                "id": message_id,
                "date": 1_700_000_000,
                "from_id": user_id,
                "peer_id": user_id,
                "text": text,
                "out": 0,
            },
        },
    }


@pytest.mark.django_db
def test_vk_callback_rejects_foreign_group_id(settings) -> None:
    settings.VK_CALLBACK_SECRET = "expected-secret"
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.vk_group_id = "242719752"
    site.save()
    client = Client()
    response = client.post(
        "/api/integrations/vk/callback/",
        data={
            "type": "message_new",
            "group_id": 999,
            "secret": "expected-secret",
            "object": {"message": {"id": 1, "from_id": 1, "text": "x"}},
        },
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_vk_callback_rejects_bad_secret(settings) -> None:
    settings.VK_CALLBACK_SECRET = "expected-secret"
    settings.VK_CALLBACK_CONFIRMATION = "abc123"
    client = Client()
    response = client.post(
        "/api/integrations/vk/callback/",
        data={"type": "message_new", "secret": "wrong"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_vk_callback_confirmation_returns_plain_text(settings) -> None:
    settings.VK_CALLBACK_SECRET = "expected-secret"
    settings.VK_CALLBACK_CONFIRMATION = "confirm-token-xyz"
    client = Client()
    response = client.post(
        "/api/integrations/vk/callback/",
        data={"type": "confirmation", "group_id": 1, "secret": "expected-secret"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.content.decode() == "confirm-token-xyz"


@pytest.mark.django_db
def test_vk_callback_confirmation_without_secret_like_vk_ui(settings) -> None:
    """VK URL check POSTs confirmation with group_id only (no secret field)."""
    settings.VK_CALLBACK_SECRET = "expected-secret"
    settings.VK_CALLBACK_CONFIRMATION = "confirm-token-xyz"
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.vk_group_id = "242719752"
    site.save()
    client = Client()
    response = client.post(
        "/api/integrations/vk/callback/",
        data={"type": "confirmation", "group_id": 242719752},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.content.decode() == "confirm-token-xyz"


@pytest.mark.django_db
def test_vk_callback_enqueues_message_new(settings) -> None:
    settings.VK_CALLBACK_SECRET = "expected-secret"
    settings.VK_CALLBACK_CONFIRMATION = "x"
    client = Client()
    event = _message_new_event(user_id=9002, text="hello")
    event["secret"] = "expected-secret"
    with patch("social.tasks.process_vk_callback_task.delay") as delay:
        response = client.post(
            "/api/integrations/vk/callback/",
            data=event,
            content_type="application/json",
        )
    assert response.status_code == 200
    assert response.content.decode() == "ok"
    delay.assert_called_once()


@pytest.mark.django_db
def test_free_text_opens_vk_support_thread() -> None:
    with patch(
        "social.vk_bot.send_to_vk_user",
        return_value=PublishResult(ok=True, external_id="42"),
    ):
        handle_vk_callback(_message_new_event(user_id=9002, text="Нужен привод DA10"))
    from supportchat.models import Channel, Conversation

    conv = Conversation.objects.get(channel=Channel.VK, external_user_id="9002")
    assert conv.messages.filter(body__icontains="DA10").exists()


@pytest.mark.django_db
def test_menu_action_replies_with_keyboard() -> None:
    with patch(
        "social.vk_bot.send_to_vk_user",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_vk_callback(_message_new_event(user_id=9010, text="/catalog"))
    assert pub.called
    assert pub.call_args.kwargs.get("keyboard") or len(pub.call_args.args) > 2


@pytest.mark.django_db
def test_chatid_reply_without_keyboard() -> None:
    """VK messages.send with keyboard needs community chat-bot mode; /chatid is plain."""
    with patch(
        "social.vk_bot.send_to_vk_user",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_vk_callback(_message_new_event(user_id=9011, text="/chatid"))
    assert pub.called
    assert pub.call_args.kwargs.get("keyboard") is None


@pytest.mark.django_db
def test_start_command_sends_welcome_not_support() -> None:
    with patch(
        "social.vk_bot.send_vk_welcome",
        return_value=PublishResult(ok=True),
    ) as welcome:
        handle_vk_callback(_message_new_event(user_id=9003, text="/start"))
    from supportchat.models import Channel, Conversation

    assert not Conversation.objects.filter(
        channel=Channel.VK,
        external_user_id="9003",
    ).exists()
    welcome.assert_called_once_with("9003")


def test_vk_write_link_uses_screen_name(settings) -> None:
    settings.VK_COMMUNITY_SCREEN_NAME = "hoocon_russia"
    assert vk_community_write_link() == "https://vk.me/hoocon_russia"
