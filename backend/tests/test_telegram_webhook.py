"""Tests for Telegram bot webhook (/start welcome with cover)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_telegram_webhook_rejects_bad_secret(settings) -> None:
    """Missing or wrong secret token returns 403."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    client = APIClient()
    url = reverse("telegram-webhook")

    bare = client.post(url, data={"update_id": 1}, format="json")
    assert bare.status_code == 403

    wrong = client.post(
        url,
        data={"update_id": 1},
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
    )
    assert wrong.status_code == 403


@pytest.mark.django_db
def test_telegram_webhook_start_sends_photo(settings, tmp_path) -> None:
    """/start replies via multipart sendPhoto with welcome caption."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    settings.SITE_URL = "https://hoocon.ru"
    cover = tmp_path / "welcome.webp"
    cover.write_bytes(b"WEBPFAKE")
    settings.TELEGRAM_WELCOME_PHOTO_PATH = str(cover)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":77}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    client = APIClient()
    payload = {
        "update_id": 10,
        "message": {
            "message_id": 1,
            "chat": {"id": 4242, "type": "private"},
            "text": "/start",
        },
    }
    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        response = client.post(
            reverse("telegram-webhook"),
            data=payload,
            format="json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    req = mocked.call_args.args[0]
    assert "sendPhoto" in req.full_url
    assert "multipart/form-data" in req.headers.get("Content-type", "")
    raw = req.data
    assert b"4242" in raw
    assert b"HOOCON" in raw
    assert b"hoocon_moscow" in raw
    assert b"WEBPFAKE" in raw


@pytest.mark.django_db
def test_telegram_webhook_ignores_non_command_without_send(settings) -> None:
    """Plain text does not trigger a Bot API call (not a support inbox)."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    client = APIClient()
    with patch("social.publishers.urlopen") as mocked:
        response = client.post(
            reverse("telegram-webhook"),
            data={
                "update_id": 11,
                "message": {
                    "message_id": 2,
                    "chat": {"id": 1, "type": "private"},
                    "text": "здравствуйте",
                },
            },
            format="json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
        )
    assert response.status_code == 200
    mocked.assert_not_called()


@pytest.mark.django_db
def test_telegram_webhook_channel_command_sends_message(settings) -> None:
    """/channel uses sendMessage with channel link."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":8}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        response = APIClient().post(
            reverse("telegram-webhook"),
            data={
                "update_id": 12,
                "message": {
                    "message_id": 3,
                    "chat": {"id": 9, "type": "private"},
                    "text": "/channel@HooconMsk_bot",
                },
            },
            format="json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
        )
    assert response.status_code == 200
    req = mocked.call_args.args[0]
    assert "sendMessage" in req.full_url
    body = json.loads(req.data.decode("utf-8"))
    assert "hoocon_moscow" in body["text"]


def test_parse_bot_command_strips_bot_suffix() -> None:
    """Command parser accepts /start@BotName form."""
    from social.telegram_bot import parse_bot_command

    assert parse_bot_command("/start@HooconMsk_bot") == "start"
    assert parse_bot_command("/HELP") == "help"
    assert parse_bot_command("hello") is None
