"""Enrich HVA std/Q SKUs from English datasheets; optionally attach local media.

Usage::

    poetry run python manage.py enrich_hva
    poetry run python manage.py enrich_hva --dry-run
    poetry run python manage.py enrich_hva --with-media
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.hva_local_media import apply_hva_local_media
from catalog.etl.series_copy_hva import apply_hva_enrichment


class Command(BaseCommand):
    """Ensure HVA catalog tiles + datasheet ТТХ (+ optional local photos)."""

    help = "Enrich HVA: ensure 5/10/20/40 ±Q cards, ТТХ from manuals, optional media."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count only, do not write.",
        )
        parser.add_argument(
            "--with-media",
            action="store_true",
            help="Also attach product / dimensions / wiring from HV seria photos.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run ensure + enrich (+ media)."""
        dry_run = bool(options["dry_run"])
        stats = apply_hva_enrichment(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        ensure = stats.get("ensure") or {}
        if stats.get("error"):
            self.stdout.write(self.style.ERROR(f"{prefix}{stats['error']}"))
            return
        families = ", ".join(f"{name}×{count}" for name, count in sorted(stats["by_family"].items()))
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}HVA ensure: products+={ensure.get('products_created', 0)} "
                f"skus+={ensure.get('skus_created', 0)}; "
                f"enriched skus={stats['skus']} updated={stats['updated']} "
                f"attrs={stats['attributes']}" + (f" ({families})" if families else ""),
            ),
        )
        if options["with_media"]:
            media = apply_hva_local_media(dry_run=dry_run)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{prefix}HVA media: created={media['created']} "
                    f"updated={media['updated']} skipped={media['skipped']}",
                ),
            )
            for warn in media.get("warnings") or []:
                self.stdout.write(self.style.WARNING(f"  ! {warn}"))
