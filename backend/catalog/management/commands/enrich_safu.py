"""Enrich SA..FU fire/smoke series from datasheet canon."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_safu import apply_safu_enrichment


class Command(BaseCommand):
    """Apply Belimo-RU / manual ТТХ for all SAFU products and SKUs."""

    help = "Enrich SAFU: shared manual attrs + torque/voltage/thermal editions."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count planned writes without touching the DB.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_safu_enrichment`."""
        dry_run = bool(options.get("dry_run"))
        stats = apply_safu_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}SAFU enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attributes={stats['attributes']}",
            ),
        )
