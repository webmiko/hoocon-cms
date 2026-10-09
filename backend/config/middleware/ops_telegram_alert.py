"""Queue Telegram ops alerts for unhandled HTTP 5xx responses."""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class OpsTelegramAlertMiddleware:
    """Notify ops chats when Django returns HTTP 500+ (deduped)."""

    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponse],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        self._maybe_alert(request, response)
        return response

    def _maybe_alert(self, request: HttpRequest, response: HttpResponse) -> None:
        if settings.DEBUG or response.status_code < 500:
            return
        path = request.path or "/"
        if path.startswith("/api/health"):
            return

        from accounts.tasks import send_ops_telegram_alert_task
        from config.ops_alerts import ops_alert_dedup_seconds, ops_telegram_chat_ids

        if not ops_telegram_chat_ids():
            return

        method = (request.method or "GET").upper()
        dedup_key = f"http{response.status_code}:{path}"
        title = f"HTTP {response.status_code} на {settings.SITE_URL.rstrip('/')}{path}"
        body = f"{method} {path}"
        try:
            if not cache.add(f"ops_alert_queued:v1:{dedup_key}", 1, timeout=ops_alert_dedup_seconds()):
                return
            send_ops_telegram_alert_task.delay(
                title=title,
                body=body,
                dedup_key=dedup_key,
            )
        except Exception:
            logger.exception("ops alert not queued for %s", dedup_key)
