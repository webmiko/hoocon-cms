"""Attach media-webp montage / emergency wiring / SAF72 tiles.

Usage::

    poetry run python manage.py attach_media_webp_extras
    poetry run python manage.py attach_media_webp_extras --dry-run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.hv_media_webp import default_media_webp_root
from catalog.etl.media_webp_extras import apply_media_webp_extras


class Command(BaseCommand):
    """Attach montage, emergency-feedback, and SAF72 tiles from media-webp."""

    help = "Attach montage / emergency wiring / SAF72 from media-webp pack."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument("--root", type=str, default="", help="Override pack dir.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        root_opt = str(options.get("root") or "").strip()
        photo_root = Path(root_opt) if root_opt else default_media_webp_root()
        summary = apply_media_webp_extras(dry_run=dry_run, photo_root=photo_root)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}montage={summary['montage']} emergency={summary['emergency']} "
            f"saf72_photo={summary['saf72_photo']} saf72_schema={summary['saf72_schema']} "
            f"demoted_tilda={summary['demoted_tilda_montage']} "
            f"demoted_emergency_non_qa={summary['demoted_emergency_non_qa']}",
        )
        if summary.get("missing"):
            self.stdout.write(f"missing: {', '.join(summary['missing'])}")
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
