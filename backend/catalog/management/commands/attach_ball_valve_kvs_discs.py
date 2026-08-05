"""Attach Kvs disc crops to brass 8100 edition SKUs.

Usage::

    poetry run python manage.py attach_ball_valve_kvs_discs
    poetry run python manage.py attach_ball_valve_kvs_discs --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ball_valve_kvs_discs import apply_ball_valve_kvs_discs


class Command(BaseCommand):
    """Link local Kvs-disc WebP crops to 8100-bv* edition SKUs."""

    help = "Attach расходный диск Kvs crops to brass 8100 edition SKUs."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Plan only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach and print a short summary."""
        dry_run = bool(options["dry_run"])
        summary = apply_ball_valve_kvs_discs(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        if summary.get("error"):
            self.stderr.write(self.style.ERROR(f"{prefix}{summary['error']}"))
            return
        self.stdout.write(
            f"{prefix}Kvs discs: created={summary['created']} "
            f"updated={summary['updated']} skipped={summary['skipped']} "
            f"missing_pack={summary['missing_pack']}",
        )
        for key, count in sorted(summary["by_key"].items()):
            self.stdout.write(f"  {key}: {count}")
        self.stdout.write(self.style.SUCCESS(f"{prefix}Kvs disc media synced."))
