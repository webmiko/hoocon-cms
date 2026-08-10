"""Create BR-M / BR-ML adapter Product/SKU cards from partner catalog copy.

Usage::

    poetry run python manage.py ensure_br_adapters
    poetry run python manage.py ensure_br_adapters --dry-run
    poetry run python manage.py ensure_br_adapters --force-images
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ensure_br_adapters import ensure_br_adapters


class Command(BaseCommand):
    """Ensure BV BR adapter cards (BR-M / BR-ML) with partner photos."""

    help = "Ensure BR-M / BR-ML adapter cards (copy + photos from partner)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--force-images",
            action="store_true",
            help="Re-download partner photos even when a published image exists.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run adapter ensure."""
        dry_run = bool(options["dry_run"])
        force_images = bool(options["force_images"])
        summary = ensure_br_adapters(dry_run=dry_run, force_images=force_images)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}products={summary['products_created']} "
            f"skus={summary['skus_created']} "
            f"images={summary.get('images')}",
        )
        if summary.get("error"):
            self.stderr.write(self.style.ERROR(str(summary["error"])))
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
