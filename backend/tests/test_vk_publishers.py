"""VK publisher helpers (wall post, DM)."""

from __future__ import annotations

from unittest.mock import patch

from social.publishers import publish_vk, publish_vk_dm


def test_publish_vk_dm_requires_non_empty_text() -> None:
    result = publish_vk_dm(user_id="123", text="   ")
    assert not result.ok
    assert "empty" in result.error.casefold()


def test_publish_vk_wall_post_text_only() -> None:
    with patch(
        "social.publishers.vk_api_call",
        return_value=({"response": 99}, ""),
    ):
        result = publish_vk(group_id="242719752", text="Hello wall")
    assert result.ok
    assert result.external_id == "99"


def test_publish_vk_skips_when_group_invalid() -> None:
    result = publish_vk(group_id="not-a-id", text="x")
    assert result.skipped


def test_publish_vk_dm_success() -> None:
    with patch(
        "social.publishers.vk_api_call",
        return_value=({"response": 1001}, ""),
    ):
        result = publish_vk_dm(user_id="42", text="Привет")
    assert result.ok
    assert result.external_id == "1001"
