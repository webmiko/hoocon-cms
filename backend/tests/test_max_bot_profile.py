"""Tests for MAX bot profile setup and welcome replies."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from social.max_bot import compose_welcome_text, handle_max_update
from social.max_bot_profile import (
    bot_avatar_path,
    bot_commands_payload,
    bot_description,
    setup_bot,
)
from social.publishers import PublishResult


def test_bot_avatar_uses_dedicated_logo() -> None:
    """Bot profile avatar is the square Hoocon H logo, not channel welcome cover."""
    path = bot_avatar_path()
    assert path is not None
    assert path.name == "max-bot-avatar.png"


def test_bot_description_mentions_channel() -> None:
    """Profile text points users to the official MAX channel."""
    text = bot_description()
    assert "max.ru" in text
    assert "/start" in text


def test_bot_commands_exclude_staff_chatid() -> None:
    """Public command menu must not expose /chatid."""
    names = {row["name"] for row in bot_commands_payload()}
    assert "start" in names
    assert "chatid" not in names


def test_compose_welcome_mentions_brand_and_channel() -> None:
    """In-chat welcome mirrors channel tone and links."""
    text = compose_welcome_text()
    assert "Добро пожаловать" in text
    assert "max.ru" in text


@pytest.mark.django_db
def test_start_reply_attaches_cover_image() -> None:
    """`/start` welcome includes cover image token before inline keyboard."""
    with (
        patch("sitesettings.credentials.max_bot_token", return_value="token"),
        patch("social.max_bot.welcome_cover_path", return_value=Path("/tmp/cover.webp")),
        patch(
            "social.max_http.max_upload_image",
            return_value="img-token",
        ),
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as pub,
    ):
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 1, "first_name": "A", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.start", "text": "/start"},
                },
            },
        )
    attachments = pub.call_args.kwargs["attachments"]
    assert attachments[0]["type"] == "image"
    assert attachments[0]["payload"]["token"] == "img-token"
    assert attachments[1]["type"] == "inline_keyboard"


def test_setup_bot_patches_profile() -> None:
    """setup_bot uploads avatar and PATCH /me with description and commands."""
    with (
        patch(
            "social.max_bot_profile.bot_avatar_path",
            return_value=Path("/tmp/cover.webp"),
        ),
        patch("social.max_bot_profile.max_upload_image", return_value="img-token") as upload,
        patch(
            "social.max_bot_profile.max_json_request",
            return_value=(200, {"success": True}),
        ) as api,
    ):
        result = setup_bot("token")
    upload.assert_called_once()
    assert api.call_args.args[0] == "PATCH"
    assert api.call_args.args[1] == "/me"
    body = api.call_args.kwargs["payload"]
    assert body["photo"] == {"token": "img-token"}
    assert body["description"]
    assert body["commands"]
    assert result["profile_status"] == "200"
