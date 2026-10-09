"""Webhook idempotency: duplicate messenger updates are skipped."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache

from social.webhook_dedup import webhook_dedup_key, webhook_once


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


def test_max_button_taps_on_same_alert_are_distinct() -> None:
    """Ключ нажатия строился по mid сообщения бота — второе нажатие на том же алерте терялось."""

    def tap(callback_id: str) -> dict:
        return {
            "update_type": "message_callback",
            "callback": {"callback_id": callback_id, "user": {"user_id": 1}},
            "message": {"body": {"mid": "mid.alert"}},
        }

    first, second = webhook_dedup_key("max", tap("cb.1")), webhook_dedup_key("max", tap("cb.2"))
    assert first == "max:message_callback:cb:cb.1"
    assert first != second


def test_webhook_once_skips_duplicate_telegram() -> None:
    update = {"update_id": 7}
    with webhook_once("telegram", update) as first:
        assert first is True
    with webhook_once("telegram", update) as again:
        assert again is False


def test_webhook_once_failure_leaves_update_retryable() -> None:
    update = {"update_id": 8}
    with pytest.raises(OSError), webhook_once("telegram", update) as first:
        assert first is True
        raise OSError("bot api down")
    with webhook_once("telegram", update) as retry:
        assert retry is True


def test_webhook_once_blocks_concurrent_delivery() -> None:
    update = {"update_id": 9}
    with webhook_once("telegram", update) as first, webhook_once("telegram", update) as parallel:
        assert first is True
        assert parallel is False


def test_process_telegram_task_skips_duplicate() -> None:
    """Celery task does not call handler when update_id was already seen."""
    from social.tasks import process_telegram_update_task

    update = {"update_id": 99, "message": {"text": "ping"}}
    with patch("social.telegram_bot.handle_telegram_update") as handler:
        process_telegram_update_task(update)
        process_telegram_update_task(update)
    handler.assert_called_once()


def test_process_telegram_task_retry_after_failure_runs_handler() -> None:
    """Ключ ставился до обработки: autoretry после OSError считал апдейт дублем и терял сообщение."""
    from social.tasks import process_telegram_update_task

    update = {"update_id": 100, "message": {"text": "ping"}}
    with patch("social.telegram_bot.handle_telegram_update", side_effect=[OSError("timeout"), None]) as handler:
        with pytest.raises(OSError):
            process_telegram_update_task.run(update)
        process_telegram_update_task.run(update)
    assert handler.call_count == 2


def test_sync_fallback_failure_leaves_update_retryable() -> None:
    import logging

    from social.webhooks import accept_bot_webhook

    calls: list[dict] = []

    def broken_enqueue(_payload: dict) -> None:
        raise ConnectionError("redis down")

    def handler(payload: dict) -> None:
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("boom")

    kwargs = {
        "channel": "telegram",
        "payload": {"update_id": 5},
        "enqueue": broken_enqueue,
        "handle_sync": handler,
        "logger": logging.getLogger("test"),
    }
    assert accept_bot_webhook(**kwargs).data == {"ok": True, "handler_failed": True}
    assert accept_bot_webhook(**kwargs).data == {"ok": True, "processed_sync": True}
    assert accept_bot_webhook(**kwargs).data == {"ok": True, "duplicate": True}
