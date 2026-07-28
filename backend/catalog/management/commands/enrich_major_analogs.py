"""Fill empty Product/SKU analogs with major-brand curated lists.

Usage::

    poetry run python manage.py enrich_major_analogs
    poetry run python manage.py enrich_major_analogs --dry-run
    poetry run python manage.py enrich_major_analogs --force
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_major_analogs import apply_major_analogs_enrichment


class Command(BaseCommand):
    """Write Belimo / Siemens / Honeywell / … analogs onto gap products."""

    help = "Fill empty analogs_text for DAMQU, SA7MU, HVA/HVD (+Q/QX) with major brands only (left-RF focus)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count only, do not write.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing analogs_text on matching products.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_major_analogs_enrichment`."""
        dry_run = bool(options["dry_run"])
        force = bool(options["force"])
        stats = apply_major_analogs_enrichment(dry_run=dry_run, force=force)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}major analogs: products={stats['products']}, "
                f"skus={stats['skus']}, skipped_filled={stats['skipped_filled']}, "
                f"slugs={stats['slugs']}",
            ),
        )
