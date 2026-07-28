"""Create catalog Products/SKUs missing vs 2022 Russian AI albums.

Usage::

    poetry run python manage.py ensure_ai_catalog_gaps
    poetry run python manage.py ensure_ai_catalog_gaps --dry-run
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ensure_ai_catalog_gaps import ensure_ai_catalog_gaps


class Command(BaseCommand):
    """Ensure DAMQU / SA7MU / HVD-40 cards from AI album gaps."""

    help = "Ensure Products/SKUs missing vs 2022 AI albums in media-webp."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run gap ensure."""
        dry_run = bool(options["dry_run"])
        summary = ensure_ai_catalog_gaps(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}products={summary['products_created']} skus={summary['skus_created']}",
        )
        if summary.get("error"):
            self.stderr.write(self.style.ERROR(str(summary["error"])))
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
