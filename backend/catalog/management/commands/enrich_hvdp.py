"""Create HVD-3P / HVD-5P cards from the Russian manuals.

Usage::

    poetry run python manage.py enrich_hvdp
    poetry run python manage.py enrich_hvdp --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_hvdp import apply_hvdp_enrichment


class Command(BaseCommand):
    """Ensure HVD-3P/5P products and fill ТТХ, photos and PDFs."""

    help = "Create unpublished HVD-3P/5P products from the RU manuals."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only, do not write.")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_hvdp_enrichment`."""
        dry_run = bool(options["dry_run"])
        stats = apply_hvdp_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}HVDP: products={stats['products_created']}, "
                f"skus={stats['skus_created']}, attributes={stats['attributes']}, "
                f"images={stats['images']}, pdfs={stats['pdfs']}",
            ),
        )
        if stats.get("error"):
            self.stderr.write(self.style.ERROR(str(stats["error"])))
