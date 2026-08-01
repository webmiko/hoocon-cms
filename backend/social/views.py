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

from social.telegram_bot import handle_telegram_update

logger = logging.getLogger("hoocon.social")

_TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_THROTTLE_SCOPE = "telegram_webhook"


class TelegramWebhookView(APIView):
    """POST /api/integrations/telegram/webhook/ — Bot API updates.

    Validates ``X-Telegram-Bot-Api-Secret-Token`` against
    ``TELEGRAM_WEBHOOK_SECRET``. Always returns JSON ``{"ok": true}`` on
    accepted requests so Telegram does not retry forever on handler bugs
    after auth succeeded.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _THROTTLE_SCOPE

    def post(self, request: Request) -> Response:
        """Accept a Telegram Update and optionally reply to a command."""
        expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "").strip()
        provided = (request.headers.get(_TELEGRAM_SECRET_HEADER) or "").strip()
        if not expected or provided != expected:
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data
        if not isinstance(payload, dict):
            return Response({"ok": True}, status=status.HTTP_200_OK)

        try:
            handle_telegram_update(payload)
        except Exception as exc:
            # Never leak update body / PII; log exception type only.
            logger.warning("telegram_webhook_handler_failed error=%s", type(exc).__name__)
        return Response({"ok": True}, status=status.HTTP_200_OK)
