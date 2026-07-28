"""Stamp first_published_at on the HV catalog wave (Новинки backfill).

Usage::

    poetry run python manage.py stamp_hv_newness
    poetry run python manage.py stamp_hv_newness --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.newness import stamp_hv_newness


class Command(BaseCommand):
    """Backfill «Новинки» timestamps for HVA / HVD-Q / P / QX."""

    help = "Stamp first_published_at on published HV-wave SKUs (empty only)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run HV newness stamp."""
        dry_run = bool(options["dry_run"])
        summary = stamp_hv_newness(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}matched={summary['matched']} updated={summary['updated']}",
            ),
        )
