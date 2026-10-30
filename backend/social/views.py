"""Public API views for social integrations (Telegram / MAX / VK webhooks)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from config.secret_compare import secrets_equal
from social.webhooks import accept_bot_webhook

logger = logging.getLogger("hoocon.social")

_TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_MAX_SECRET_HEADER = "X-Max-Bot-Api-Secret"
_TELEGRAM_THROTTLE_SCOPE = "telegram_webhook"
_MAX_THROTTLE_SCOPE = "max_webhook"
_VK_THROTTLE_SCOPE = "vk_webhook"


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
        if not expected or not secrets_equal(expected, provided):
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
        if not expected or not secrets_equal(expected, provided):
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


class VkCallbackView(APIView):
    """POST /api/integrations/vk/callback/ — VK Callback API (community messages).

    Validates ``secret`` in the JSON body against ``VK_CALLBACK_SECRET``.
    ``confirmation`` events return plain-text ``VK_CALLBACK_CONFIRMATION``;
    other events enqueue Celery work and respond with ``ok``.
    """

    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = _VK_THROTTLE_SCOPE

    def post(self, request: Request) -> HttpResponse | Response:
        payload = request.data
        if not isinstance(payload, dict):
            return HttpResponse("ok", content_type="text/plain; charset=utf-8")

        from sitesettings.models import SiteSettings

        event_type = (payload.get("type") or "").strip()
        expected = getattr(settings, "VK_CALLBACK_SECRET", "").strip()
        provided = str(payload.get("secret") or "").strip()

        site = SiteSettings.load()
        configured_gid = (site.vk_group_id or "").strip().lstrip("-")
        payload_gid = str(payload.get("group_id") or "").strip().lstrip("-")
        if configured_gid:
            if not payload_gid or configured_gid != payload_gid:
                return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        # VK sends ``confirmation`` without ``secret`` when verifying the URL.
        if event_type == "confirmation":
            if expected and provided and not secrets_equal(expected, provided):
                return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)
        elif not expected or not secrets_equal(expected, provided):
            return Response({"ok": False}, status=status.HTTP_403_FORBIDDEN)

        if event_type == "confirmation":
            confirmation = getattr(settings, "VK_CALLBACK_CONFIRMATION", "").strip()
            if not confirmation:
                return Response(
                    {"ok": False, "error": "confirmation_not_configured"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return HttpResponse(confirmation, content_type="text/plain; charset=utf-8")

        from social.tasks import process_vk_callback_task
        from social.vk_bot import handle_vk_callback

        try:
            process_vk_callback_task.delay(payload)
        except Exception as exc:
            logger.warning(
                "vk_callback_enqueue_failed error=%s falling_back_sync",
                type(exc).__name__,
            )
            try:
                from social.webhook_dedup import webhook_once

                with webhook_once("vk", payload) as first:
                    if first:
                        handle_vk_callback(payload)
            except Exception as sync_exc:
                logger.error(
                    "vk_callback_handler_failed error=%s",
                    type(sync_exc).__name__,
                    exc_info=sync_exc,
                )

        return HttpResponse("ok", content_type="text/plain; charset=utf-8")
