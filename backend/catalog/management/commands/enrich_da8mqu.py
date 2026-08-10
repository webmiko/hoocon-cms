"""Enrich DA..MQU series (5/8/16/24 Нм) from EN manuals + Belimo RU glossary."""

from __future__ import annotations

import re
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.belimo_analogs import primary_belimo_code_for_sku
from catalog.etl.da_sa_media_webp import clone_damqu_images_from_donor
from catalog.etl.html_text import filter_analogs_for_sku
from catalog.etl.manual_pdfs import clone_damqu_manuals_from_donor
from catalog.etl.media_webp_extras import demote_tilda_montages_where_local_exists
from catalog.etl.series_copy_damqu import (
    CANONICAL_NMS,
    apply_damqu_enrichment,
    damqu_product_queryset,
    retire_damqu_noncanonical_nm,
)
from catalog.etl.series_copy_major_analogs import build_damqu_analogs
from catalog.models import SKU

_NM_FROM_SLUG = re.compile(r"(?i)da(?P<nm>\d+)mqu")


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
        analogs_n = 0
        belimo_n = 0
        for product in damqu_product_queryset().order_by("slug"):
            match = _NM_FROM_SLUG.search(product.slug or "")
            if match is None:
                continue
            nm = int(match.group("nm"))
            if nm not in CANONICAL_NMS:
                continue
            text = build_damqu_analogs(nm)
            analogs_n += 1
            if not dry_run:
                product.analogs_text = text
                product.save(update_fields=["analogs_text", "updated_at"])
            skus = (
                SKU.objects.filter(product=product, is_published=True)
                .select_related("product", "product__category")
                .prefetch_related("attribute_values__attribute")
            )
            for sku in skus:
                scoped = filter_analogs_for_sku(text, sku.sku_code)
                if not dry_run:
                    sku.analogs_text = scoped
                    sku.save(update_fields=["analogs_text", "updated_at"])
                    sku.refresh_from_db()
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
                f"{prefix}DAMQU analogs rewritten: products={analogs_n}, belimo_updated={belimo_n}",
            ),
        )
