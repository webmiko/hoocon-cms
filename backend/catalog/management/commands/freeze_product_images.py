"""Freeze approved product photos/diagrams against ETL overwrites.

Usage::

    poetry run python manage.py freeze_product_images --scope schemes --dry-run
    poetry run python manage.py freeze_product_images --scope all --yes
    poetry run python manage.py freeze_product_images --scope schemes --series hva --yes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.product_image_freeze import default_reports_dir, freeze_product_images
from catalog.models import SKU


def _split_values(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Split repeated comma-separated CLI values into clean items."""
    result: list[str] = []
    for value in values:
        for item in str(value).split(","):
            item = item.strip()
            if item:
                result.append(item)
    return tuple(dict.fromkeys(result))


def _read_exclude_file(path: str) -> tuple[str, ...]:
    """Read owner exclusion articles from a text file (one or CSV per line)."""
    lines = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return _split_values(lines)


class Command(BaseCommand):
    """Mark selected ProductImage rows locked and write a verification manifest."""

    help = "Freeze ProductImage rows (dry-run by default); write private_media/reports/product-images-manifest-*.csv."

    def add_arguments(self, parser: Any) -> None:
        """Register freeze filters and confirmation flags."""
        parser.add_argument(
            "--scope",
            choices=("schemes", "all"),
            required=True,
            help="schemes = diagram files (wiring/dimensions/montazhnaya/termodatchik/flow etc.); all = every image.",
        )
        parser.add_argument(
            "--sku",
            action="append",
            default=[],
            help="Limit to SKU code(s); repeat or comma-separate.",
        )
        parser.add_argument(
            "--series",
            action="append",
            default=[],
            help="Limit to SKU code prefix(es), e.g. hva, h81, da5fu; repeat or comma-separate.",
        )
        parser.add_argument(
            "--exclude-sku",
            action="append",
            default=[],
            help="Exclude SKU code(s) from freezing; repeat or comma-separate.",
        )
        parser.add_argument(
            "--exclude-file",
            default="",
            help="Text file with owner-approved exclusion articles (blank lines and # comments ignored).",
        )
        parser.add_argument(
            "--reports-dir",
            default="",
            help="Manifest directory (default: private_media/reports/).",
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="List rows without locking (default).")
        mode.add_argument("--yes", action="store_true", help="Apply the freeze and write the manifest.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run dry-run or apply the freeze."""
        sku_codes = _split_values(options.get("sku") or [])
        series_prefixes = _split_values(options.get("series") or [])
        exclude_sku_codes = _split_values(options.get("exclude_sku") or [])
        exclude_file = str(options.get("exclude_file") or "").strip()
        if exclude_file:
            exclude_sku_codes = tuple(dict.fromkeys([*exclude_sku_codes, *_read_exclude_file(exclude_file)]))

        unknown = [code for code in sku_codes if not SKU.objects.filter(sku_code__iexact=code).exists()]
        if unknown:
            raise CommandError(f"Unknown SKU code(s): {', '.join(unknown)}")

        reports_dir = Path(options.get("reports_dir") or default_reports_dir())
        dry_run = not bool(options.get("yes"))
        summary = freeze_product_images(
            scope=options["scope"],
            dry_run=dry_run,
            reports_dir=reports_dir,
            sku_codes=sku_codes,
            series_prefixes=series_prefixes,
            exclude_sku_codes=exclude_sku_codes,
        )
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}scope={summary['scope']} matched={summary['matched']} "
            f"would_lock={summary['would_lock']} already_locked={summary['already_locked']}",
        )
        if dry_run:
            for row in summary["rows"]:
                self.stdout.write(f"{row.sku.sku_code}\t{row.image.name}")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"locked={summary['locked']} already_locked={summary['already_locked']} "
                f"manifest={summary['manifest']}",
            ),
        )
