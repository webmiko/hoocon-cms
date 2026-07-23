"""Create/enrich HVD-…F smoke-damper products from English manuals.

Usage::

    poetry run python manage.py enrich_hvdf
    poetry run python manage.py enrich_hvdf --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_hvdf import apply_hvdf_enrichment


class Command(BaseCommand):
    """Ensure HVD-3F/5F catalog rows and apply ТТХ from manuals."""

    help = "Create HVD-…F products/SKUs and enrich copy + attributes."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count only, do not write.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_hvdf_enrichment`."""
        dry_run = bool(options["dry_run"])
        stats = apply_hvdf_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        ensure = stats.get("ensure") or {}
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}HVDF: products={stats['products']}, "
                f"skus={stats['skus']}, attributes={stats['attributes']}, "
                f"created_products={ensure.get('products_created', 0)}, "
                f"created_skus={ensure.get('skus_created', 0)}",
            ),
        )
