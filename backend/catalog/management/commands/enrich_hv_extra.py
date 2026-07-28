"""Seed + enrich HVD-Q and HV*QX capacitor families.

Usage::

    poetry run python manage.py enrich_hv_extra
    poetry run python manage.py enrich_hv_extra --with-media
    poetry run python manage.py enrich_hv_extra --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_copy_hv_extra import apply_hv_extra_enrichment


class Command(BaseCommand):
    """Ensure catalog tiles for HVD-Q / capacitor QX and fill ТТХ."""

    help = "Enrich HV extras: HVD-Q and HVA/HVD*QX capacitor (not HVA-P)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--with-media",
            action="store_true",
            help="Attach local HVD photos where available.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run ensure + enrich."""
        dry_run = bool(options["dry_run"])
        stats = apply_hv_extra_enrichment(
            dry_run=dry_run,
            with_media=bool(options["with_media"]),
        )
        prefix = "[dry-run] " if dry_run else ""
        for err in stats.get("errors") or []:
            self.stdout.write(self.style.ERROR(f"{prefix}{err}"))
        for key in ("ensure_hvd_q", "ensure_qx"):
            block = stats[key]
            self.stdout.write(
                f"{prefix}{key}: products+={block.get('products_created', 0)} skus+={block.get('skus_created', 0)}",
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}enriched skus={stats['skus']} attrs={stats['attributes']} "
                f"media +{stats['media_created']} ~{stats['media_updated']}",
            ),
        )
        manuals = stats.get("manuals") or {}
        if manuals:
            self.stdout.write(
                f"{prefix}manuals +{manuals.get('created', 0)} "
                f"~{manuals.get('updated', 0)} skip={manuals.get('skipped', 0)}",
            )
            for warn in manuals.get("warnings") or []:
                self.stdout.write(self.style.WARNING(f"{prefix}{warn}"))
