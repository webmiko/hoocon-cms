"""Public API views for social integrations (Telegram webhook)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger("hoocon.social")

_TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_THROTTLE_SCOPE = "telegram_webhook"


class TelegramWebhookView(APIView):
    """POST /api/integrations/telegram/webhook/ — Bot API updates.

    Validates ``X-Telegram-Bot-Api-Secret-Token`` against
    ``TELEGRAM_WEBHOOK_SECRET``. Always returns JSON ``{"ok": true}`` on
    accepted requests so Telegram does not retry forever on handler bugs
    after auth succeeded. Processing runs in Celery so egress retries do not
    block the webhook response.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE_SCOPE

    def post(self, request: Request) -> Response:
        """Accept a Telegram Update and enqueue reply handling."""
        expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "").strip()
        provided = (request.headers.get(_TELEGRAM_SECRET_HEADER) or "").strip()
        if not expected or provided != expected:
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        if not isinstance(payload, dict):
            return Response({"ok": True}, status=status.HTTP_200_OK)

        from social.tasks import process_telegram_update_task

        try:
            process_telegram_update_task.delay(payload)
        except Exception as exc:
            # Broker down: fall back to sync so /start still works in local/dev.
            logger.warning(
                "telegram_webhook_enqueue_failed error=%s falling_back_sync",
                type(exc).__name__,
            )
            try:
                from social.telegram_bot import handle_telegram_update

                handle_telegram_update(payload)
            except Exception as sync_exc:
                logger.warning(
                    "telegram_webhook_handler_failed error=%s",
                    type(sync_exc).__name__,
                )
        return Response({"ok": True}, status=status.HTTP_200_OK)
