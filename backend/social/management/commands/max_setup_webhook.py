"""Register MAX bot webhook subscription (POST /subscriptions).

Usage::

    poetry run python manage.py max_setup_webhook
    poetry run python manage.py max_setup_webhook --show
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sitesettings.credentials import max_bot_token
from social.max_http import max_json_request

_MAX_API = "https://platform-api2.max.ru"
_UPDATE_TYPES = ("bot_started", "message_created", "message_callback")


class Command(BaseCommand):
    """Upsert MAX webhook subscription for hoocon.ru."""

    help = "Register MAX webhook (bot_started + message_created) on platform-api2.max.ru."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--show",
            action="store_true",
            help="List current subscriptions and exit.",
        )

    def handle(self, *args: object, **options: object) -> None:
        del args
        token = max_bot_token()
        if not token:
            raise CommandError("MAX_BOT_TOKEN не задан (Admin или .env).")

        if options.get("show"):
            self._print_subscriptions(token)
            return

        secret = getattr(settings, "MAX_WEBHOOK_SECRET", "").strip()
        if not secret:
            raise CommandError("MAX_WEBHOOK_SECRET не задан в .env.")

        site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
        webhook_url = f"{site}/api/integrations/max/webhook/"
        payload = {
            "url": webhook_url,
            "update_types": list(_UPDATE_TYPES),
            "secret": secret,
        }
        status, data = max_json_request("POST", "/subscriptions", token, payload=payload)
        if status >= 400 or not data.get("success", True):
            raise CommandError(f"POST /subscriptions failed: HTTP {status} {data!r}")
        self.stdout.write(
            self.style.SUCCESS(
                f"MAX webhook registered: {webhook_url} (types={','.join(_UPDATE_TYPES)})",
            ),
        )

    def _print_subscriptions(self, token: str) -> None:
        try:
            status, data = max_json_request("GET", "/subscriptions", token)
        except OSError as exc:
            raise CommandError(f"MAX API error: {type(exc).__name__}") from exc
        if status >= 400:
            raise CommandError(f"GET /subscriptions failed: HTTP {status}")
        self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
