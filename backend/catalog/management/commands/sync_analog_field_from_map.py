"""One-off: copy primary Belimo ``AnalogMap`` article into ``SKU.analog_belimo_code``."""

from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand

from catalog.models import SKU, AnalogMap, normalize_analog_code


def _primary_belimo_code(rows: list[AnalogMap]) -> str:
    rows = sorted(rows, key=lambda row: (row.torque_nm or 0, row.foreign_code or ""))
    return (rows[0].foreign_code or "").strip() if rows else ""


class Command(BaseCommand):
    """Align the card field with active Belimo rows in AnalogMap (reference only)."""

    help = (
        "For each SKU with an active Belimo AnalogMap row, set analog_belimo_code "
        "to the primary article (torque, then code). SKUs without a map row are untouched."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without writing",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run"))
        maps = AnalogMap.objects.filter(is_active=True, brand__iexact="belimo")
        by_sku: dict[int, list[AnalogMap]] = defaultdict(list)
        for row in maps:
            by_sku[row.sku_id].append(row)

        updated = 0
        skipped = 0
        for sku_id, rows in sorted(by_sku.items()):
            expected = _primary_belimo_code(rows)
            if not expected:
                continue
            sku = SKU.objects.filter(pk=sku_id).only("id", "sku_code", "analog_belimo_code").first()
            if sku is None:
                continue
            current = (sku.analog_belimo_code or "").strip()
            if normalize_analog_code(current) == normalize_analog_code(expected):
                skipped += 1
                continue
            self.stdout.write(f"  {sku.sku_code}: {current or '∅'} → {expected}")
            if not dry_run:
                SKU.objects.filter(pk=sku_id).update(analog_belimo_code=expected)
            updated += 1

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}sync: updated={updated}, already_ok={skipped}"),
        )
