"""Backfill lightweight ``image_card`` WebP for catalog / mobile tiles.

Usage::

    poetry run python manage.py generate_product_image_cards
    poetry run python manage.py generate_product_image_cards --limit 50
    poetry run python manage.py generate_product_image_cards --force
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.webp import attach_image_card, backfill_missing_image_cards
from catalog.models import ProductImage


class Command(BaseCommand):
    """Generate card/mobile WebP derivatives from full ProductImage files."""

    help = "Backfill ProductImage.image_card (≤720px WebP) for list/mobile payload."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N missing rows (default: all).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate cards even when image_card already exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run backfill or forced regenerate."""
        limit = options.get("limit")
        if options["force"]:
            qs = ProductImage.objects.exclude(image="").order_by("id")
            if limit is not None:
                qs = qs[: max(0, int(limit))]
            scanned = 0
            written = 0
            errors = 0
            for row in qs.iterator(chunk_size=50):
                scanned += 1
                try:
                    if attach_image_card(row):
                        row.save(update_fields=["image_card", "updated_at"])
                        written += 1
                except (OSError, ValueError):
                    errors += 1
            summary = {"scanned": scanned, "written": written, "errors": errors}
        else:
            summary = backfill_missing_image_cards(limit=limit)

        self.stdout.write(
            self.style.SUCCESS(
                f"image_card: scanned={summary['scanned']} written={summary['written']} errors={summary['errors']}",
            ),
        )
