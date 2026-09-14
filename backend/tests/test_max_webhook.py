"""Tests for MAX bot webhook and update handling."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

from social.max_bot import (
    compose_chatid_reply,
    handle_max_update,
    main_menu_keyboard,
    parse_start_payload,
    resolve_start_action,
)
from social.publishers import PublishResult


@pytest.mark.django_db
def test_max_webhook_rejects_bad_secret(settings) -> None:
    """Webhook without valid X-Max-Bot-Api-Secret returns 403."""
    settings.MAX_WEBHOOK_SECRET = "expected-secret"
    client = Client()
    response = client.post(
        "/api/integrations/max/webhook/",
        data={"update_type": "bot_started"},
        content_type="application/json",
        HTTP_X_MAX_BOT_API_SECRET="wrong",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_max_webhook_accepts_valid_secret(settings) -> None:
    """Valid secret enqueues update and returns ok."""
    settings.MAX_WEBHOOK_SECRET = "expected-secret"
    client = Client()
    with patch("social.tasks.process_max_update_task.delay") as delay:
        response = client.post(
            "/api/integrations/max/webhook/",
            data={"update_type": "bot_started", "user": {"user_id": 1}},
            content_type="application/json",
            HTTP_X_MAX_BOT_API_SECRET="expected-secret",
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    delay.assert_called_once()


@pytest.mark.django_db
def test_chatid_command_returns_user_id() -> None:
    """/chatid replies with user id and does not open support thread."""
    with patch(
        "social.max_bot.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 424242, "first_name": "Val", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.1", "text": "/chatid"},
                },
            },
        )
    assert pub.called
    assert "424242" in pub.call_args.kwargs["text"]
    assert "user_id" in pub.call_args.kwargs["text"].casefold()


def test_compose_chatid_reply_plain() -> None:
    assert "424242" in compose_chatid_reply("424242")


def test_start_payload_parsing() -> None:
    """Deep links ?start=catalog map to catalog action."""
    assert parse_start_payload("/start") == "support"
    assert parse_start_payload("/start catalog") == "catalog"
    assert resolve_start_action("kp") == "consultation"


@pytest.mark.django_db
def test_start_catalog_reply() -> None:
    """`/start catalog` sends catalog link, not a support thread."""
    with patch(
        "social.max_bot.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 1, "first_name": "A", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.2", "text": "/start catalog"},
                },
            },
        )
    assert pub.called
    assert "/catalog" in pub.call_args.kwargs["text"]


def test_main_menu_has_legal_links() -> None:
    """Menu includes privacy, terms and oferta URLs."""
    rows = main_menu_keyboard()
    assert rows
    keyboard = rows[0]["payload"]["buttons"]
    flat_urls = [btn["url"] for row in keyboard for btn in row]
    assert any("/privacy-policy" in url for url in flat_urls)
    assert any("/terms" in url for url in flat_urls)
    assert any("/oferta" in url for url in flat_urls)


@pytest.mark.django_db
def test_dialog_cleared_sends_welcome() -> None:
    """Clearing bot chat history triggers welcome with cover again."""
    with (
        patch("sitesettings.credentials.max_bot_token", return_value="token"),
        patch("social.max_bot.welcome_cover_path", return_value=None),
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as pub,
    ):
        handle_max_update(
            {
                "update_type": "dialog_cleared",
                "user": {"user_id": 501, "first_name": "Клиент"},
            },
        )
    assert pub.called
    assert "Добро пожаловать" in pub.call_args.kwargs["text"]


@pytest.mark.django_db
def test_free_text_opens_support_thread() -> None:
    """Client question is stored in supportchat as MAX channel."""
    with patch(
        "social.max_bot.publish_max",
        return_value=PublishResult(ok=True),
    ):
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 9001, "first_name": "Клиент", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.support", "text": "Нужен привод DA10"},
                },
            },
        )
    from supportchat.models import Channel, Conversation

    conv = Conversation.objects.get(channel=Channel.MAX, external_user_id="9001")
    assert conv.messages.filter(body__icontains="DA10").exists()
