"""Shared webhook acceptance for Telegram and MAX bot integrations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from rest_framework import status
from rest_framework.response import Response


def accept_bot_webhook(
    *,
    channel: str,
    payload: object,
    enqueue: Callable[[dict[str, Any]], Any],
    handle_sync: Callable[[dict[str, Any]], None],
    logger: logging.Logger,
) -> Response:
    """Validate payload shape, enqueue async work, or fall back to sync handling.

    Always returns HTTP 200 with ``ok: true`` after auth succeeded so messengers
    do not retry forever on handler bugs. Failures are visible via
    ``handler_failed`` in the JSON body and ``*_webhook_handler_failed`` logs.
    """
    if not isinstance(payload, dict):
        return Response({"ok": True, "skipped": True}, status=status.HTTP_200_OK)

    try:
        enqueue(payload)
        return Response({"ok": True, "queued": True}, status=status.HTTP_200_OK)
    except Exception as exc:
        logger.warning(
            "%s_webhook_enqueue_failed error=%s falling_back_sync",
            channel,
            type(exc).__name__,
        )

    try:
        handle_sync(payload)
        return Response({"ok": True, "processed_sync": True}, status=status.HTTP_200_OK)
    except Exception as sync_exc:
        logger.error(
            "%s_webhook_handler_failed error=%s",
            channel,
            type(sync_exc).__name__,
            exc_info=sync_exc,
        )
        return Response(
            {"ok": True, "handler_failed": True},
            status=status.HTTP_200_OK,
        )
