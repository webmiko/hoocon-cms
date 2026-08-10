"""Backfill SKU descriptions to drop foreign 24/230 / A-AS blocks.

Usage:
  poetry run python manage.py scope_sku_descriptions
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.html_text import dedupe_description_lines
from catalog.etl.sku_variant import filter_description_for_variant, parse_sku_variant
from catalog.models import SKU


class Command(BaseCommand):
    """Rewrite each SKU.description for its electrical edition only."""

    help = "Scope SKU descriptions to matching voltage/control variant"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        updated = 0
        for sku in SKU.objects.select_related("product").iterator():
            source = sku.description or sku.product.description or ""
            if not source.strip():
                continue
            scoped = filter_description_for_variant(
                dedupe_description_lines(source),
                parse_sku_variant(sku.sku_code),
            )
            if scoped == (sku.description or ""):
                continue
            updated += 1
            if dry_run:
                continue
            sku.description = scoped
            sku.save(update_fields=["description", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(f"SKU descriptions scoped: {updated} dry_run={dry_run}"),
        )
