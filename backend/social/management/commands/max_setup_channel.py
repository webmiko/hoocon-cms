"""Configure MAX channel profile, welcome post and print interaction codes.

Usage::

    poetry run python manage.py max_setup_channel --codes
    poetry run python manage.py max_setup_channel
    poetry run python manage.py max_setup_channel --dry-run
"""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sitesettings.credentials import max_bot_token
from social.max_bot import interaction_codes_markdown
from social.max_channel import (
    channel_description,
    channel_title,
    channel_welcome_text,
    setup_channel,
)


class Command(BaseCommand):
    """Patch channel profile, post welcome with cover + buttons, optional pin."""

    help = "Настроить канал MAX: описание, обложка, приветственный пост и кнопки."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--chat-id",
            default="",
            help="ID канала (по умолчанию MAX_CHAT_ID из .env или Admin).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что будет отправлено, без вызовов API.",
        )
        parser.add_argument(
            "--no-pin",
            action="store_true",
            help="Не закреплять приветственный пост.",
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Отправить push при смене описания/аватара канала.",
        )
        parser.add_argument(
            "--codes",
            action="store_true",
            help="Вывести коды взаимодействия (deep link и команды) и выйти.",
        )
        parser.add_argument(
            "--write-codes",
            metavar="PATH",
            default="",
            help="Сохранить коды в markdown-файл (например docs/max-integration.md).",
        )

    def handle(self, *args: object, **options: object) -> None:
        del args
        if options.get("codes") or options.get("write_codes"):
            self._print_or_write_codes(str(options.get("write_codes") or ""))
            if options.get("codes"):
                return

        token = max_bot_token()
        if not token:
            raise CommandError("MAX_BOT_TOKEN не задан (Admin или .env).")

        chat_id = self._resolve_chat_id(str(options.get("chat_id") or ""))
        if not chat_id:
            raise CommandError("MAX_CHAT_ID не задан (Admin → Интеграции или .env).")

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("DRY RUN — API не вызывается"))
            self.stdout.write(f"chat_id: {chat_id}")
            self.stdout.write(f"title: {channel_title()}")
            self.stdout.write(f"description:\n{channel_description()}")
            self.stdout.write(f"welcome:\n{channel_welcome_text()}")
            return

        try:
            result = setup_channel(
                token,
                chat_id,
                pin_welcome=not options.get("no_pin"),
                notify_profile=bool(options.get("notify")),
            )
        except OSError as exc:
            raise CommandError(f"MAX API error: {type(exc).__name__}") from exc
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Канал MAX настроен: chat_id={result['chat_id']} welcome_mid={result.get('welcome_mid') or '—'}",
            ),
        )
        if options.get("write_codes"):
            self._print_or_write_codes(str(options.get("write_codes")))

    def _resolve_chat_id(self, explicit: str) -> str:
        if explicit.strip():
            return explicit.strip()
        from sitesettings.models import SiteSettings

        site_id = (SiteSettings.load().max_chat_id or "").strip()
        if site_id:
            return site_id
        return os.getenv("MAX_CHAT_ID", "").strip()

    def _print_or_write_codes(self, path: str) -> None:
        text = interaction_codes_markdown()
        if path:
            target = path
            if not os.path.isabs(target):
                target = os.path.join(settings.BASE_DIR.parent, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.write("\n")
            self.stdout.write(self.style.SUCCESS(f"Коды сохранены: {target}"))
        else:
            self.stdout.write(text)
