"""Attach unique per-SKU HVA/HVD heroes from the studio PNG pack.

Usage::

    poetry run python manage.py attach_hv_sku_media
    poetry run python manage.py attach_hv_sku_media --dry-run
    poetry run python manage.py attach_hv_sku_media --root "/path/to/HV 产品"
    poetry run python manage.py attach_hv_sku_media --include-spring
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.hv_sku_media import (
    apply_hv_sku_media,
    default_hv_sku_photo_root,
    default_hv_spring_photo_root,
)


class Command(BaseCommand):
    """Replace HVA/HVD product photos with unique per-SKU studio cutouts."""

    help = "Convert and attach unique HV product heroes from the per-SKU studio pack."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--root",
            type=str,
            default="",
            help="Override HV 产品 directory.",
        )
        parser.add_argument(
            "--include-spring",
            action="store_true",
            help="Also scan 弹簧复位产品 (*P); attaches only when SKU exists.",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Only SKUs without an own hv-sku hero; exact file match, no QX fallback.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        root_opt = str(options.get("root") or "").strip()
        spring_opt = str(options.get("spring_root") or "").strip()
        include_spring = bool(options.get("include_spring"))
        only_missing = bool(options.get("only_missing"))
        photo_root = Path(root_opt) if root_opt else default_hv_sku_photo_root()
        spring_root = Path(spring_opt) if spring_opt else default_hv_spring_photo_root()
        summary = apply_hv_sku_media(
            dry_run=dry_run,
            photo_root=photo_root,
            include_spring=include_spring,
            spring_root=spring_root if include_spring else None,
            only_missing=only_missing,
        )
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}attached={summary['attached']} "
            f"created={summary['created']} updated={summary['updated']} "
            f"already_own={summary.get('already_own', 0)} "
            f"qx_fallback={summary['qx_fallback']} "
            f"root={summary['photo_root']}",
        )
        if summary["missing_sku"]:
            self.stdout.write(
                f"no catalog SKU for files: {', '.join(summary['missing_sku'])}",
            )
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
