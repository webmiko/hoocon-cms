"""Regression tests for shared Telegram/MAX webhook acceptance."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from social.webhooks import accept_bot_webhook


@pytest.mark.django_db
def test_accept_bot_webhook_queues_valid_payload() -> None:
    """Valid dict payloads are enqueued and marked queued in the response."""
    enqueue = MagicMock()
    handle_sync = MagicMock()
    payload = {"update_type": "bot_started", "user": {"user_id": 1}}

    response = accept_bot_webhook(
        channel="max",
        payload=payload,
        enqueue=enqueue,
        handle_sync=handle_sync,
        logger=logging.getLogger("test.social"),
    )

    assert response.status_code == 200
    assert response.data == {"ok": True, "queued": True}
    enqueue.assert_called_once_with(payload)
    handle_sync.assert_not_called()


@pytest.mark.django_db
def test_accept_bot_webhook_handler_failed_is_logged(caplog) -> None:
    """Sync fallback failures set handler_failed without turning into HTTP 500."""
    enqueue = MagicMock(side_effect=RuntimeError("broker_down"))
    handle_sync = MagicMock(side_effect=ValueError("handler_broken"))

    with caplog.at_level(logging.ERROR, logger="hoocon.social"):
        response = accept_bot_webhook(
            channel="telegram",
            payload={"update_id": 1},
            enqueue=enqueue,
            handle_sync=handle_sync,
            logger=logging.getLogger("hoocon.social"),
        )

    assert response.status_code == 200
    assert response.data == {"ok": True, "handler_failed": True}
    assert any("telegram_webhook_handler_failed" in rec.message for rec in caplog.records)
