"""Enrich DA..FQU fast spring-return series from datasheet canon."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_dafqu import apply_dafqu_enrichment


class Command(BaseCommand):
    """Apply manual ТТХ for DA..FQU products and SKUs."""

    help = "Enrich DAFQU: fast spring-return damper actuators."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count planned writes without touching the DB.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options.get("dry_run"))
        stats = apply_dafqu_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        ensure = stats.get("ensure") or {}
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAFQU: products+={ensure.get('products_created', 0)}, "
                f"skus+={ensure.get('skus_created', 0)}; enriched products={stats['products']}, "
                f"skus={stats['skus']}, attributes={stats['attributes']}",
            ),
        )
