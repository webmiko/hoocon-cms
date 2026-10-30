"""Celery task wiring for VK callbacks."""

from __future__ import annotations

from unittest.mock import patch

from social.tasks import process_vk_callback_task


def test_process_vk_callback_task_invokes_handler() -> None:
    payload = {"type": "message_new", "group_id": 1, "object": {}}
    with patch("social.vk_bot.handle_vk_callback") as handler:
        with patch("social.webhook_dedup.webhook_once") as once:
            once.return_value.__enter__.return_value = True
            process_vk_callback_task(payload)
    handler.assert_called_once_with(payload)
