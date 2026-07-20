"""Persist primary Belimo analog codes onto ``SKU.analog_belimo_code``."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.etl.belimo_analogs import primary_belimo_code_for_sku
from catalog.models import SKU


class Command(BaseCommand):
    """Fill ``analog_belimo_code`` from card «Аналоги» text or ТТХ inference."""

    help = (
        "Set SKU.analog_belimo_code from Belimo lines in analogs_text "
        "(edition-filtered) or infer from category / moment / voltage / "
        "control / aux switch. Use --dry-run to preview."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite non-empty analog_belimo_code",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run"))
        force = bool(options.get("force"))
        qs = (
            SKU.objects.filter(is_published=True)
            .select_related("product", "product__category")
            .prefetch_related("attribute_values__attribute")
            .order_by("sku_code")
        )
        updated = 0
        skipped = 0
        empty = 0
        for sku in qs:
            primary = primary_belimo_code_for_sku(sku)
            if not primary:
                empty += 1
                continue
            current = (sku.analog_belimo_code or "").strip()
            if current and not force:
                if current.casefold() == primary.casefold():
                    skipped += 1
                    continue
                skipped += 1
                continue
            if current.casefold() == primary.casefold():
                skipped += 1
                continue
            self.stdout.write(f"  {sku.sku_code}: {current or '∅'} → {primary}")
            if not dry_run:
                sku.analog_belimo_code = primary
                sku.save(update_fields=["analog_belimo_code"])
            updated += 1
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}belimo analogs: updated={updated}, skipped={skipped}, empty={empty}",
            ),
        )
