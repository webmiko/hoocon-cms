"""Enrich bare HVD air on/off (5/10/20/40 Нм, not Q/QX).

Usage::

    poetry run python manage.py enrich_hvd_air
    poetry run python manage.py enrich_hvd_air --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_hvd_air import apply_hvd_air_enrichment


class Command(BaseCommand):
    """Apply full ТТХ for bare HVD air damper SKUs."""

    help = "Enrich bare HVD air products/SKUs (moment, voltage, area, aux, …)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")

    def handle(self, *args: object, **options: object) -> None:
        """Run HVD air enrich."""
        stats = apply_hvd_air_enrichment(dry_run=bool(options.get("dry_run")))
        if stats["skus"] == 0:
            self.stderr.write(self.style.ERROR("No bare HVD air SKUs found"))
            return
        prefix = "[dry-run] " if stats.get("dry_run") else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}HVD air enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attr_writes={stats['attributes']}, "
                f"by_nm={stats.get('by_nm')}",
            ),
        )
