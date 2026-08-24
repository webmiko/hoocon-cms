"""Attach brass 8100 / iron 8100Q product heroes from media-webp (+ archive Iron/).

Usage::

    poetry run python manage.py attach_ball_valve_media_webp
    poetry run python manage.py attach_ball_valve_media_webp --dry-run
    poetry run python manage.py attach_ball_valve_media_webp --root /path/to/media-webp
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ball_valve_media_webp import apply_ball_valve_media_webp


class Command(BaseCommand):
    """Replace 8100 / 8100Q body photos from the media-webp (and Iron) packs."""

    help = "Optimize and attach brass 8100 + iron 8100Q product heroes."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--root",
            type=str,
            default="",
            help="Override pack directory (skips archive Iron/ fallback).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        root_opt = str(options.get("root") or "").strip()
        photo_root = Path(root_opt) if root_opt else None
        summary = apply_ball_valve_media_webp(dry_run=dry_run, photo_root=photo_root)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}created={summary['created']} updated={summary['updated']} "
            f"skipped={summary['skipped']} root={summary['photo_root']}",
        )
        if summary["missing_products"]:
            self.stdout.write(f"missing: {', '.join(summary['missing_products'])}")
        self.stdout.write(json.dumps(summary["by_stem"], ensure_ascii=False, indent=2))
