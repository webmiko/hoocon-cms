"""Attach 3-way flow schematic to brass 8100 BV3xx SKUs.

Usage::

    poetry run python manage.py attach_ball_valve_flow_scheme
    poetry run python manage.py attach_ball_valve_flow_scheme --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ball_valve_flow_scheme import apply_ball_valve_flow_scheme


class Command(BaseCommand):
    """Link flow-direction WebP to 3-way 8100-bv3* edition SKUs."""

    help = "Attach схема направления потока to 3-way brass 8100 SKUs."

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
        summary = apply_ball_valve_flow_scheme(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        if summary.get("error"):
            self.stderr.write(self.style.ERROR(f"{prefix}{summary['error']}"))
            return
        self.stdout.write(
            f"{prefix}Flow scheme: created={summary['created']} "
            f"updated={summary['updated']} skipped={summary['skipped']}",
        )
        self.stdout.write(self.style.SUCCESS(f"{prefix}Flow scheme media synced."))
