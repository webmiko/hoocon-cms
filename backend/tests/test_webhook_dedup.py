"""Webhook idempotency: duplicate messenger updates are skipped."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache

from social.webhook_dedup import begin_webhook_processing, webhook_dedup_key


@pytest.fixture(autouse=True)
def clear_dedup_cache() -> None:
    cache.clear()


def test_webhook_dedup_key_telegram_update_id() -> None:
    assert webhook_dedup_key("telegram", {"update_id": 42}) == "telegram:42"


def test_webhook_dedup_key_max_message_mid() -> None:
    update = {
        "update_type": "message_created",
        "message": {"body": {"mid": "mid.99", "text": "hi"}},
    }
    assert webhook_dedup_key("max", update) == "max:message_created:mid.99"


def test_begin_webhook_processing_skips_duplicate_telegram() -> None:
    update = {"update_id": 7}
    assert begin_webhook_processing("telegram", update) is True
    assert begin_webhook_processing("telegram", update) is False


def test_process_telegram_task_skips_duplicate() -> None:
    """Celery task does not call handler when update_id was already seen."""
    from social.tasks import process_telegram_update_task

    update = {"update_id": 99, "message": {"text": "ping"}}
    with patch("social.telegram_bot.handle_telegram_update") as handler:
        process_telegram_update_task(update)
        process_telegram_update_task(update)
    handler.assert_called_once()
