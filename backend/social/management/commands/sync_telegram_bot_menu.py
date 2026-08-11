"""Sync Telegram bot command menu (setMyCommands).

Usage::

    poetry run python manage.py sync_telegram_bot_menu
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from social.telegram_bot import BOT_COMMANDS, sync_bot_commands


class Command(BaseCommand):
    """Register reply-menu commands: channel / site / help / start."""

    help = "Sync Telegram Bot API setMyCommands (start / channel / site / help — RU descriptions)."

    def handle(self, *args: object, **options: object) -> None:
        del args, options
        result = sync_bot_commands()
        if result.skipped:
            raise CommandError(result.error or "Telegram не настроен")
        if not result.ok:
            raise CommandError(result.error or "setMyCommands failed")
        labels = ", ".join(f"/{c['command']} — {c['description']}" for c in BOT_COMMANDS)
        self.stdout.write(self.style.SUCCESS(f"Telegram menu synced: {labels}"))
