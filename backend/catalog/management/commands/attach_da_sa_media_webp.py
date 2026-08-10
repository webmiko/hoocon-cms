"""Attach DA/SA product heroes from the local media-webp pack.

Usage::

    poetry run python manage.py attach_da_sa_media_webp
    poetry run python manage.py attach_da_sa_media_webp --dry-run
    poetry run python manage.py attach_da_sa_media_webp --root /path/to/media-webp
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.da_sa_media_webp import apply_da_sa_media_webp
from catalog.etl.hv_media_webp import default_media_webp_root


class Command(BaseCommand):
    """Replace DA/SA product photos from the media-webp cutout pack."""

    help = "Optimize and attach DA/SA product heroes from media-webp folder."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--root",
            type=str,
            default="",
            help="Override media-webp directory.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        root_opt = str(options.get("root") or "").strip()
        photo_root = Path(root_opt) if root_opt else default_media_webp_root()
        summary = apply_da_sa_media_webp(dry_run=dry_run, photo_root=photo_root)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}created={summary['created']} updated={summary['updated']} "
            f"skipped={summary['skipped']} unmatched={len(summary.get('unmatched') or [])} "
            f"root={summary['photo_root']}",
        )
        unmatched = summary.get("unmatched") or []
        if unmatched:
            preview = ", ".join(unmatched[:20])
            more = f" (+{len(unmatched) - 20})" if len(unmatched) > 20 else ""
            self.stdout.write(f"unmatched: {preview}{more}")
        self.stdout.write(json.dumps(summary["by_stem"], ensure_ascii=False, indent=2))
