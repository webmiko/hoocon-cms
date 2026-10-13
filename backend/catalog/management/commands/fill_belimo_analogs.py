"""Persist primary Belimo analog codes onto ``SKU.analog_belimo_code``."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.etl.belimo_analogs import (
    _sku_uses_ds_as_control_editions,
    belimo_code_is_direct_for_sku,
    belimo_code_is_thermal,
    belimo_code_matches_control,
    belimo_codes_for_sku,
    normalize_belimo_code,
    primary_belimo_code_for_sku,
    sku_takes_no_analogs,
)
from catalog.etl.sku_variant import parse_sku_variant, sku_code_is_thermal
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
        cleared = 0
        for sku in qs:
            primary = primary_belimo_code_for_sku(sku)
            current = (sku.analog_belimo_code or "").strip()
            if not primary:
                empty += 1
                # Large-scope facets read the field directly: drop non-direct leftovers.
                if current and (sku_takes_no_analogs(sku) or not belimo_code_is_direct_for_sku(current, sku.sku_code)):
                    self.stdout.write(f"  {sku.sku_code}: {current} → ∅ (нет прямого аналога)")
                    if not dry_run:
                        sku.analog_belimo_code = ""
                        sku.save(update_fields=["analog_belimo_code"])
                    cleared += 1
                continue
            if current and not force:
                if current.casefold() == primary.casefold():
                    skipped += 1
                    continue
                # Auto-refresh clear mismatches without --force:
                # shared DS/AS on/off Belimo on modulating SKU, or DST without FST/-T.
                control = parse_sku_variant(sku.sku_code).control
                control_mismatch = _sku_uses_ds_as_control_editions(
                    sku.sku_code,
                ) and not belimo_code_matches_control(current, control)
                thermal_mismatch = (
                    sku_code_is_thermal(sku.sku_code)
                    and belimo_code_is_thermal(primary)
                    and current.casefold() != primary.casefold()
                ) or (
                    # Plain DS/… kept a thermal Belimo from a shared voltage list.
                    (not sku_code_is_thermal(sku.sku_code)) and belimo_code_is_thermal(current)
                )
                # Family / aux drift: the card «Аналоги» no longer lists this article.
                stale = normalize_belimo_code(current) not in belimo_codes_for_sku(sku)
                if not control_mismatch and not thermal_mismatch and not stale:
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
                f"{prefix}belimo analogs: updated={updated}, cleared={cleared}, skipped={skipped}, empty={empty}",
            ),
        )
