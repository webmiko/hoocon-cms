"""Enrich DA..MQU series (5/8/16/24 Нм) from EN manuals + Belimo RU glossary."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.belimo_analogs import primary_belimo_code_for_sku
from catalog.etl.da_sa_media_webp import clone_damqu_images_from_donor
from catalog.etl.manual_pdfs import clone_damqu_manuals_from_donor
from catalog.etl.media_webp_extras import demote_tilda_montages_where_local_exists
from catalog.etl.series_copy_damqu import (
    apply_damqu_enrichment,
    retire_damqu_noncanonical_nm,
)
from catalog.etl.series_copy_major_analogs import apply_major_analogs_enrichment
from catalog.models import SKU


class Command(BaseCommand):
    """Apply series copy and edition ТТХ for canonical DA..MQU tiles."""

    help = "Enrich DA..MQU (5/8/16/24 Нм); unpublish DA10/DA20 with 301 to DA8/DA24."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")

    def handle(self, *args: object, **options: object) -> None:
        """Retire non-canonical Nm, then enrich remaining tiles."""
        dry_run = bool(options.get("dry_run"))
        retired = retire_damqu_noncanonical_nm(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.WARNING(
                f"{prefix}DAMQU retire 10/20: "
                f"skus_unpublished={retired['skus_unpublished']}, "
                f"redirects={retired['redirects']}",
            ),
        )
        stats = apply_damqu_enrichment(dry_run=dry_run)
        if stats["products"] == 0:
            self.stderr.write(self.style.ERROR("No DA..MQU products found"))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAMQU enriched: products={stats['products']}, "
                f"skus={stats['skus']}, attr_writes={stats['attributes']}, "
                f"by_nm={stats.get('by_nm')}",
            ),
        )
        media = clone_damqu_images_from_donor(dry_run=dry_run)
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAMQU media from DA8 → 16/24: "
                f"targets={media['targets']}, created={media['created']}, "
                f"updated={media['updated']}, skipped={media['skipped']}",
            ),
        )
        demoted = demote_tilda_montages_where_local_exists(dry_run=dry_run)
        self.stdout.write(
            self.style.WARNING(
                f"{prefix}DAMQU demoted Tilda montage dupes: {demoted}",
            ),
        )
        manuals = clone_damqu_manuals_from_donor(dry_run=dry_run)
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAMQU manuals from DA8 → 16/24: "
                f"targets={manuals['targets']}, created={manuals['created']}, "
                f"updated={manuals['updated']}, skipped={manuals['skipped']}",
            ),
        )
        analogs = apply_major_analogs_enrichment(dry_run=dry_run, force=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}major analogs: products={analogs['products']}, "
                f"skus={analogs['skus']}, skipped_filled={analogs['skipped_filled']}",
            ),
        )
        belimo_n = 0
        damqu = (
            SKU.objects.filter(sku_code__iregex=r"(?i)^da\d+mqu", is_published=True)
            .select_related("product", "product__category")
            .prefetch_related("attribute_values__attribute")
            .order_by("sku_code")
        )
        for sku in damqu:
            primary = primary_belimo_code_for_sku(sku)
            if not primary:
                continue
            current = (sku.analog_belimo_code or "").strip()
            if current.casefold() == primary.casefold():
                continue
            belimo_n += 1
            if not dry_run:
                sku.analog_belimo_code = primary
                sku.save(update_fields=["analog_belimo_code"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DAMQU Belimo card codes: updated={belimo_n}",
            ),
        )
