"""Enrich SA..MU product/SKU copy and ТТХ from English manuals.

Usage::

    poetry run python manage.py enrich_samu
    poetry run python manage.py enrich_samu --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_samu import apply_samu_enrichment


class Command(BaseCommand):
    """Apply smoke-damper ТТХ for all SAMU products and SKUs."""

    help = "Enrich SAMU: shared manual attrs + torque/voltage/thermal editions."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count only, do not write.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_samu_enrichment`."""
        dry_run = bool(options["dry_run"])
        stats = apply_samu_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}SAMU enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attributes={stats['attributes']}",
            ),
        )
