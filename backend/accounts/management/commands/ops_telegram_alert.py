"""Send a deduped ops alert to Telegram (cron / monitor-health)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from config.ops_alerts import send_ops_telegram_alert


class Command(BaseCommand):
    help = "Send a deduped ops Telegram alert (monitor-health, manual smoke)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--message", required=True, help="Alert body text.")
        parser.add_argument(
            "--title",
            default="Hoocon monitor",
            help="Alert title (default: Hoocon monitor).",
        )
        parser.add_argument(
            "--dedup-key",
            default="monitor",
            help="Dedup cache key (default: monitor).",
        )

    def handle(self, *args, **options) -> None:
        sent = send_ops_telegram_alert(
            title=str(options["title"]),
            body=str(options["message"]),
            dedup_key=str(options["dedup_key"]),
        )
        self.stdout.write(self.style.SUCCESS(f"ops telegram sent={sent}"))
