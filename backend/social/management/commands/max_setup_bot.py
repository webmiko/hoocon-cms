"""Configure MAX bot profile: description, avatar and command menu.

Usage::

    poetry run python manage.py max_setup_bot
    poetry run python manage.py max_setup_bot --dry-run
    poetry run python manage.py max_setup_bot --show
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from sitesettings.credentials import max_bot_token
from social.max_bot_profile import (
    bot_commands_payload,
    bot_description,
    bot_display_name,
    get_bot_profile,
    setup_bot,
)


class Command(BaseCommand):
    """PATCH /me — bot welcome profile before the first message."""

    help = "Настроить бота MAX: описание, аватар и меню команд."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--show",
            action="store_true",
            help="Показать текущий профиль бота (GET /me) и выйти.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что будет отправлено, без вызовов API.",
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Отправить push при смене описания/аватара бота.",
        )

    def handle(self, *args: object, **options: object) -> None:
        del args
        token = max_bot_token()
        if not token:
            raise CommandError("MAX_BOT_TOKEN не задан (Admin или .env).")

        if options.get("show"):
            self._print_profile(token)
            return

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("DRY RUN — API не вызывается"))
            self.stdout.write(f"name: {bot_display_name()}")
            self.stdout.write(f"description:\n{bot_description()}")
            self.stdout.write(
                f"commands: {json.dumps(bot_commands_payload(), ensure_ascii=False, indent=2)}",
            )
            return

        try:
            result = setup_bot(token, notify_profile=bool(options.get("notify")))
        except OSError as exc:
            raise CommandError(f"MAX API error: {type(exc).__name__}") from exc
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Бот MAX настроен: "
                f"name={result['name']} commands={result['commands']} "
                f"avatar={result.get('avatar') or '—'}",
            ),
        )

    def _print_profile(self, token: str) -> None:
        try:
            status, data = get_bot_profile(token)
        except OSError as exc:
            raise CommandError(f"MAX API error: {type(exc).__name__}") from exc
        if status >= 400:
            raise CommandError(f"GET /me failed: HTTP {status}")
        self.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
