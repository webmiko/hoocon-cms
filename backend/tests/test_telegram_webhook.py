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
    assert "Перейти в канал".encode() in raw
    assert "На сайт".encode() in raw
    assert "Помощь".encode() in raw
    assert b"reply_markup" in raw
    assert b"WEBPFAKE" in raw


@pytest.mark.django_db
def test_telegram_webhook_menu_button_channel(settings) -> None:
    """Reply-keyboard «Перейти в канал» triggers channel action (not ingest)."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":9}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        response = APIClient().post(
            reverse("telegram-webhook"),
            data={
                "update_id": 20,
                "message": {
                    "message_id": 4,
                    "chat": {"id": 11, "type": "private"},
                    "text": "Перейти в канал",
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
    assert body["reply_markup"]["keyboard"][0][0]["text"] == "Перейти в канал"
    assert body["reply_markup"]["is_persistent"] is True


@pytest.mark.django_db
def test_sync_telegram_bot_menu_calls_set_my_commands(settings) -> None:
    """Management helper posts setMyCommands with RU descriptions."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":true}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    from social.telegram_bot import sync_bot_commands

    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        result = sync_bot_commands()
    assert result.ok
    req = mocked.call_args.args[0]
    assert "setMyCommands" in req.full_url
    body = json.loads(req.data.decode("utf-8"))
    by_cmd = {row["command"]: row["description"] for row in body["commands"]}
    assert by_cmd["channel"] == "Перейти в канал"
    assert by_cmd["site"] == "На сайт"
    assert by_cmd["help"] == "Помощь"


@pytest.mark.django_db
def test_telegram_webhook_plain_text_goes_to_support_inbox(settings) -> None:
    """Free-form text creates a support Conversation + Message (no Bot API send)."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    from supportchat.models import Channel, Conversation, Message
    from supportchat.schedule import ensure_default_schedule

    ensure_default_schedule()
    client = APIClient()
    with patch("social.publishers.urlopen") as mocked:
        with patch("supportchat.services.is_open_now", return_value=True):
            response = client.post(
                reverse("telegram-webhook"),
                data={
                    "update_id": 11,
                    "message": {
                        "message_id": 2,
                        "chat": {"id": 777, "type": "private"},
                        "from": {"first_name": "Ivan", "last_name": "Petrov"},
                        "text": "здравствуйте",
                    },
                },
                format="json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
            )
    assert response.status_code == 200
    mocked.assert_not_called()
    conv = Conversation.objects.get(channel=Channel.TELEGRAM, external_user_id="777")
    assert conv.display_name == "Ivan Petrov"
    assert Message.objects.filter(conversation=conv, body="здравствуйте").count() == 1

    # Idempotent duplicate update
    with patch("social.publishers.urlopen") as mocked2:
        with patch("supportchat.services.is_open_now", return_value=True):
            client.post(
                reverse("telegram-webhook"),
                data={
                    "update_id": 12,
                    "message": {
                        "message_id": 2,
                        "chat": {"id": 777, "type": "private"},
                        "text": "здравствуйте",
                    },
                },
                format="json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
            )
    mocked2.assert_not_called()
    assert Message.objects.filter(conversation=conv).count() == 1


@pytest.mark.django_db
def test_staff_reply_delivers_to_telegram(settings) -> None:
    """Outbound Celery task calls publish_telegram for TG conversations."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    from django.contrib.auth import get_user_model

    from supportchat.models import Channel, Conversation
    from supportchat.services import add_staff_reply
    from supportchat.tasks import deliver_outbound_message

    user = get_user_model().objects.create_user(
        username="mgr@hoocon.ru",
        email="mgr@hoocon.ru",
        password="x",
        is_staff=True,
    )
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="999",
        display_name="Client",
    )
    msg = add_staff_reply(conv, "Ответ менеджера", author=user)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":55}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        result = deliver_outbound_message(msg.pk)
    assert result == "telegram_ok"
    req = mocked.call_args.args[0]
    assert "sendMessage" in req.full_url
    body = json.loads(req.data.decode("utf-8"))
    assert body["chat_id"] == "999"
    assert "Ответ менеджера" in body["text"]


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
    from social.telegram_bot import parse_bot_command, resolve_menu_action

    assert parse_bot_command("/start@HooconMsk_bot") == "start"
    assert parse_bot_command("/HELP") == "help"
    assert parse_bot_command("hello") is None
    assert resolve_menu_action("Перейти в канал") == "channel"
    assert resolve_menu_action("На сайт") == "site"
    assert resolve_menu_action("Помощь") == "help"
    # Former short aliases must not steal free-text (full button labels only).
    assert resolve_menu_action("канал") is None
    assert resolve_menu_action("сайт") is None
    assert resolve_menu_action("перейти в канал") == "channel"


@pytest.mark.django_db
def test_telegram_webhook_photo_caption_goes_to_support_inbox(settings) -> None:
    """Photo/document caption is ingested when ``text`` is absent."""
    settings.TELEGRAM_WEBHOOK_SECRET = "expected-secret"
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    from supportchat.models import Channel, Conversation, Message
    from supportchat.schedule import ensure_default_schedule

    ensure_default_schedule()
    with patch("social.publishers.urlopen") as mocked:
        with patch("supportchat.services.is_open_now", return_value=True):
            response = APIClient().post(
                reverse("telegram-webhook"),
                data={
                    "update_id": 40,
                    "message": {
                        "message_id": 88,
                        "chat": {"id": 555, "type": "private"},
                        "from": {"first_name": "Anna"},
                        "caption": "фото с вопросом",
                        "photo": [{"file_id": "x"}],
                    },
                },
                format="json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="expected-secret",
            )
    assert response.status_code == 200
    mocked.assert_not_called()
    conv = Conversation.objects.get(channel=Channel.TELEGRAM, external_user_id="555")
    assert Message.objects.filter(conversation=conv, body="фото с вопросом").count() == 1


@pytest.mark.django_db
def test_staff_reply_escapes_html_for_telegram(settings) -> None:
    """Outbound Telegram text escapes HTML so visitor tags are not parsed."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    from django.contrib.auth import get_user_model

    from supportchat.models import Channel, Conversation
    from supportchat.services import add_staff_reply
    from supportchat.tasks import deliver_outbound_message

    user = get_user_model().objects.create_user(
        username="esc@hoocon.ru",
        email="esc@hoocon.ru",
        password="x",
        is_staff=True,
    )
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="1001",
        display_name="Client",
    )
    msg = add_staff_reply(conv, 'Цена <b>100</b> & "ок"', author=user)

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"ok":true,"result":{"message_id":56}}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = False

    with patch("social.publishers.urlopen", return_value=mock_resp) as mocked:
        assert deliver_outbound_message(msg.pk) == "telegram_ok"
    body = json.loads(mocked.call_args.args[0].data.decode("utf-8"))
    assert body["text"] == "Цена &lt;b&gt;100&lt;/b&gt; &amp; &quot;ок&quot;"


@pytest.mark.django_db
def test_staff_reply_skips_when_already_delivered(settings) -> None:
    """Celery retry must not send Telegram again after external_message_id set."""
    settings.TELEGRAM_BOT_TOKEN = "bot-token"
    from django.contrib.auth import get_user_model

    from supportchat.models import Channel, Conversation
    from supportchat.services import add_staff_reply
    from supportchat.tasks import deliver_outbound_message

    user = get_user_model().objects.create_user(
        username="dedupe@hoocon.ru",
        email="dedupe@hoocon.ru",
        password="x",
        is_staff=True,
    )
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="42",
        display_name="Client",
    )
    msg = add_staff_reply(conv, "уже ушло", author=user)
    msg.external_message_id = "tg-99"
    msg.save(update_fields=["external_message_id"])

    with patch("social.publishers.urlopen") as mocked:
        assert deliver_outbound_message(msg.pk) == "already_delivered"
    mocked.assert_not_called()
