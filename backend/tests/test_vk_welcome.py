"""VK community welcome copy and message_allow."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from social.publishers import PublishResult
from social.vk_bot import compose_vk_welcome_text, handle_vk_callback, send_vk_welcome, vk_community_url
from social.vk_community import community_cover_path, welcome_dm_photo_path


def test_compose_vk_welcome_mentions_vk_community_not_max() -> None:
    text = compose_vk_welcome_text()
    assert "Hoocon" in text
    assert vk_community_url() in text
    assert "max.ru" not in text.casefold()


@pytest.mark.django_db
def test_message_allow_sends_welcome() -> None:
    event = {
        "type": "message_allow",
        "group_id": 242719752,
        "object": {"user_id": 4242, "key": "test"},
    }
    with patch("social.vk_bot.send_vk_welcome", return_value=PublishResult(ok=True)) as welcome:
        handle_vk_callback(event)
    welcome.assert_called_once_with("4242")


@pytest.mark.django_db
def test_start_uses_vk_welcome() -> None:
    event = {
        "type": "message_new",
        "group_id": 242719752,
        "object": {
            "message": {
                "id": 1,
                "date": 1,
                "from_id": 9003,
                "peer_id": 9003,
                "text": "/start",
                "out": 0,
            },
        },
    }
    with patch("social.vk_bot.send_vk_welcome", return_value=PublishResult(ok=True)) as welcome:
        handle_vk_callback(event)
    welcome.assert_called_once_with("9003")


def test_vk_photo_path_env_overrides_wired(settings, tmp_path) -> None:
    """VK_WELCOME_PHOTO_PATH / VK_COMMUNITY_COVER_PATH were .env-only dead knobs."""
    assert hasattr(settings, "VK_WELCOME_PHOTO_PATH")
    assert hasattr(settings, "VK_COMMUNITY_COVER_PATH")
    photo = tmp_path / "cover.png"
    photo.write_bytes(b"fake")
    settings.VK_WELCOME_PHOTO_PATH = str(photo)
    settings.VK_COMMUNITY_COVER_PATH = str(photo)
    assert welcome_dm_photo_path() == photo
    assert community_cover_path() == photo


@pytest.mark.django_db
def test_send_vk_welcome_falls_back_to_text_when_photo_missing(settings, tmp_path) -> None:
    settings.BASE_DIR = tmp_path
    with patch("social.vk_bot.publish_vk_dm", return_value=PublishResult(ok=True)) as pub:
        send_vk_welcome("12345")
    pub.assert_called_once()
    assert "Добро пожаловать" in pub.call_args.kwargs["text"]
