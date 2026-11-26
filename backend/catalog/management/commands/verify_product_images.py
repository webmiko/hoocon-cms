"""Verify frozen ProductImage files against a freeze manifest.

Usage::

    poetry run python manage.py verify_product_images
    poetry run python manage.py verify_product_images --manifest private_media/reports/product-images-manifest-….csv
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.product_image_freeze import (
    default_reports_dir,
    latest_manifest,
    verify_product_images_manifest,
)


class Command(BaseCommand):
    """Check sha256/size of files listed in a freeze manifest."""

    help = "Verify frozen ProductImage files against private_media/reports/product-images-manifest-*.csv."

    def add_arguments(self, parser: Any) -> None:
        """Register manifest and storage overrides."""
        parser.add_argument(
            "--manifest",
            default="",
            help="Manifest CSV path (default: newest product-images-manifest-*.csv in reports/).",
        )
        parser.add_argument(
            "--reports-dir",
            default="",
            help="Directory for newest-manifest lookup (default: private_media/reports/).",
        )
        parser.add_argument(
            "--media-root",
            default="",
            help="Override MEDIA_ROOT for local verification.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Verify and exit non-zero when any file drifted."""
        manifest_raw = str(options.get("manifest") or "").strip()
        if manifest_raw:
            manifest = Path(manifest_raw)
        else:
            reports_dir = Path(options.get("reports_dir") or default_reports_dir())
            manifest = latest_manifest(reports_dir) or Path()
        if not manifest or not manifest.is_file():
            raise CommandError("freeze manifest not found; pass --manifest or run freeze_product_images --yes first")

        media_root = Path(options["media_root"]) if str(options.get("media_root") or "").strip() else None
        try:
            summary = verify_product_images_manifest(manifest, media_root=media_root)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        mismatches = summary["mismatches"]
        for row in mismatches[:50]:
            self.stdout.write(f"mismatch\t{row['sku']}\t{row['image']}\t{row['reason']}")
        if len(mismatches) > 50:
            self.stdout.write(f"… and {len(mismatches) - 50} more")
        if mismatches:
            raise CommandError(f"verify_product_images: mismatches={len(mismatches)} manifest={manifest}")
        self.stdout.write(
            self.style.SUCCESS(
                f"rows={summary['rows']} checked={summary['checked']} mismatches=0 manifest={manifest}",
            ),
        )
