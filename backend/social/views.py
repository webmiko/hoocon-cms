"""Public API views for social integrations (Telegram / MAX webhooks)."""

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

from social.webhooks import accept_bot_webhook

logger = logging.getLogger("hoocon.social")

_TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_MAX_SECRET_HEADER = "X-Max-Bot-Api-Secret"
_TELEGRAM_THROTTLE_SCOPE = "telegram_webhook"
_MAX_THROTTLE_SCOPE = "max_webhook"


class TelegramWebhookView(APIView):
    """POST /api/integrations/telegram/webhook/ — Bot API updates.

    Validates ``X-Telegram-Bot-Api-Secret-Token`` against
    ``TELEGRAM_WEBHOOK_SECRET``. Processing runs in Celery so egress retries do
    not block the webhook response.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _TELEGRAM_THROTTLE_SCOPE

    def post(self, request: Request) -> Response:
        """Accept a Telegram Update and enqueue reply handling."""
        expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "").strip()
        provided = (request.headers.get(_TELEGRAM_SECRET_HEADER) or "").strip()
        if not expected or provided != expected:
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        from social.tasks import process_telegram_update_task
        from social.telegram_bot import handle_telegram_update

        return accept_bot_webhook(
            channel="telegram",
            payload=request.data,
            enqueue=process_telegram_update_task.delay,
            handle_sync=handle_telegram_update,
            logger=logger,
        )


class MaxWebhookView(APIView):
    """POST /api/integrations/max/webhook/ — MAX Bot API updates.

    Validates ``X-Max-Bot-Api-Secret`` against ``MAX_WEBHOOK_SECRET``.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _MAX_THROTTLE_SCOPE

    def post(self, request: Request) -> Response:
        """Accept a MAX Update and enqueue reply handling."""
        expected = getattr(settings, "MAX_WEBHOOK_SECRET", "").strip()
        provided = (request.headers.get(_MAX_SECRET_HEADER) or "").strip()
        if not expected or provided != expected:
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        from social.max_bot import handle_max_update
        from social.tasks import process_max_update_task

        return accept_bot_webhook(
            channel="max",
            payload=request.data,
            enqueue=process_max_update_task.delay,
            handle_sync=handle_max_update,
            logger=logger,
        )
