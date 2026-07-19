"""Enrich BV215 ball-valve series from Tilda PDP / store CSV."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_bv215 import PRODUCT_SLUG, apply_bv215_enrichment


class Command(BaseCommand):
    """Apply BV215 series copy, ТТХ cards, and gallery images."""

    help = "Enrich BV215 product/SKUs: description, attribute cards, and three Tilda gallery photos."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Rewrite copy/attrs only; do not download gallery photos.",
        )

    def handle(self, *args: object, **options: object) -> None:
        stats = apply_bv215_enrichment(
            import_images=not bool(options.get("skip_images")),
        )
        if stats["products"] == 0:
            self.stderr.write(
                self.style.ERROR(f"Product {PRODUCT_SLUG} not found"),
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"BV215 enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attr_writes={stats['attributes']}, "
                f"images_created={stats['images_created']}, "
                f"images_failed={stats['images_failed']}",
            ),
        )
