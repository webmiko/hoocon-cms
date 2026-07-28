"""Backfill HVD air (no spring) family dimensions/weight from datasheets.

Usage::

    poetry run python manage.py enrich_hvd_air_size
    poetry run python manage.py enrich_hvd_air_size --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.hvd_air_size import apply_hvd_air_size_backfill


class Command(BaseCommand):
    """Apply datasheet envelope/mass for HVD-10 and HVD-40Q families."""

    help = "Backfill HVD air dimensions/weight (family-level) for known Nm rows."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count only, do not write.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_hvd_air_size_backfill`."""
        dry_run = bool(options["dry_run"])
        stats = apply_hvd_air_size_backfill(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}HVD air size: skus={stats['skus']}, updated={stats['updated']}, skipped={stats['skipped']}",
            ),
        )
