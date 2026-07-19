"""Enrich DA8MQU series from canonical datasheet copy."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_damqu import apply_damqu_enrichment


class Command(BaseCommand):
    """Apply Belimo-RU series copy and edition ТТХ for DA8MQU."""

    help = "Enrich DA8MQU product/SKUs: description, specs, dimensions, weight."

    def handle(self, *args: object, **options: object) -> None:
        stats = apply_damqu_enrichment()
        if stats["products"] == 0:
            self.stderr.write(self.style.ERROR("Product privod-vozdushniy-da8mqu-8nm not found"))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"DA8MQU enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attr_writes={stats['attributes']}",
            ),
        )
