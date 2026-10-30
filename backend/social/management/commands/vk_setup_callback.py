"""Register VK Callback API server and enable message_new events.

Usage:
    poetry run python manage.py vk_setup_callback --show
    poetry run python manage.py vk_setup_callback --url https://hoocon.ru/api/integrations/vk/callback/
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sitesettings.credentials import vk_access_token
from sitesettings.models import SiteSettings
from social.publishers import vk_api_call


class Command(BaseCommand):
    help = "Configure VK Callback API for community messages (support chat)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--url",
            default="https://hoocon.ru/api/integrations/vk/callback/",
            help="HTTPS callback URL (must match nginx → Django).",
        )
        parser.add_argument(
            "--show",
            action="store_true",
            help="Print current callback servers and exit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned API calls without executing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        token = vk_access_token()
        site = SiteSettings.load()
        group_id = (site.vk_group_id or "").strip().lstrip("-")
        if not token or not group_id.isdigit():
            raise CommandError("VK token and numeric vk_group_id required in Admin or VK_ACCESS_TOKEN.")

        secret = getattr(settings, "VK_CALLBACK_SECRET", "").strip()
        confirmation = getattr(settings, "VK_CALLBACK_CONFIRMATION", "").strip()
        if not options["show"] and (not secret or not confirmation):
            raise CommandError(
                "Set VK_CALLBACK_SECRET and VK_CALLBACK_CONFIRMATION in .env on the server "
                "(VK Admin → Работа с API → Callback → секрет и строка подтверждения).",
            )

        if options["show"]:
            data, err = vk_api_call("groups.getCallbackServers", {"group_id": group_id})
            if data is None:
                raise CommandError(err)
            self.stdout.write(json.dumps(data.get("response", data), ensure_ascii=False, indent=2))
            return

        callback_url = (options["url"] or "").strip()
        if not callback_url.startswith("https://"):
            raise CommandError("--url must be HTTPS")

        if options["dry_run"]:
            self.stdout.write(f"Would add callback server {callback_url} for group {group_id}")
            self.stdout.write("Would enable message_new in groups.setCallbackSettings")
            return

        add_data, err = vk_api_call(
            "groups.addCallbackServer",
            {
                "group_id": group_id,
                "url": callback_url,
                "title": "Hoocon CMS",
                "secret_key": secret,
            },
        )
        if add_data is None:
            raise CommandError(err)
        server_id = add_data.get("response")
        if server_id is None:
            raise CommandError(f"Unexpected addCallbackServer response: {add_data}")

        settings_data, err = vk_api_call(
            "groups.setCallbackSettings",
            {
                "group_id": group_id,
                "server_id": str(server_id),
                "message_new": "1",
                "message_event": "1",
                "api_version": "5.199",
            },
        )
        if settings_data is None:
            raise CommandError(err)

        self.stdout.write(
            self.style.SUCCESS(
                f"VK callback server #{server_id} registered for group {group_id}. "
                f"Confirmation string in env must match VK Admin.",
            ),
        )
        self.stdout.write(
            "Ensure community token has «Сообщения сообщества» and messages are enabled in VK UI.",
        )
