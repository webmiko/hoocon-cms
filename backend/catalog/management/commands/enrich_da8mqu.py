"""Enrich DA..MQU series (5/8/10/20 Нм) from datasheet + 2022 AI album."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_damqu import apply_damqu_enrichment


class Command(BaseCommand):
    """Apply series copy and edition ТТХ for all DA..MQU tiles."""

    help = "Enrich DA..MQU products/SKUs: description, specs, dimensions, weight."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")

    def handle(self, *args: object, **options: object) -> None:
        """Run DAMQU enrich."""
        stats = apply_damqu_enrichment(dry_run=bool(options.get("dry_run")))
        if stats["products"] == 0:
            self.stderr.write(self.style.ERROR("No DA..MQU products found"))
            return
        prefix = "[dry-run] " if stats.get("dry_run") else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAMQU enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attr_writes={stats['attributes']}, "
                f"by_nm={stats.get('by_nm')}",
            ),
        )
