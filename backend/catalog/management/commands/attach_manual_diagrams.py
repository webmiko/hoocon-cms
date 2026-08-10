"""Attach wiring + dimensions diagrams from manuals / HVA / H81 catalogs.

Unpublishes legacy Tilda «Размеры и способ подключения» gallery shots (DAFU).

Usage::

    poetry run python manage.py attach_manual_diagrams
    poetry run python manage.py attach_manual_diagrams --series hva
    poetry run python manage.py attach_manual_diagrams --series h81
    poetry run python manage.py attach_manual_diagrams --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.h81_catalog_media import apply_h81_catalog_media
from catalog.etl.manual_diagrams import (
    apply_damu_manual_diagrams,
    apply_hva_manual_diagrams,
    apply_hvdf_manual_diagrams,
    apply_manual_diagrams,
    apply_safu_manual_diagrams,
    apply_samu_manual_diagrams,
)


class Command(BaseCommand):
    """Crop PDF diagrams and attach them to matching DAFU/SAFU/DAMU SKU galleries."""

    help = "Attach wiring/dimensions diagrams from manuals to product galleries."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count changes without writing images or unpublishing rows.",
        )
        parser.add_argument(
            "--series",
            choices=("all", "dafu", "safu", "damu", "samu", "hvdf", "hva", "h81"),
            default="all",
            help="Which series diagrams to attach (default: all).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run diagram attach helpers and print a short summary."""
        dry_run = bool(options.get("dry_run"))
        series = str(options.get("series") or "all")
        prefix = "[dry-run] " if dry_run else ""

        jobs: list[tuple[str, dict[str, Any]]] = []
        if series in {"all", "dafu"}:
            jobs.append(("DAFU", apply_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "safu"}:
            jobs.append(("SAFU", apply_safu_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "damu"}:
            jobs.append(("DAMU", apply_damu_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "samu"}:
            jobs.append(("SAMU", apply_samu_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "hvdf"}:
            jobs.append(("HVDF", apply_hvdf_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "hva"}:
            jobs.append(("HVA", apply_hva_manual_diagrams(dry_run=dry_run)))
        if series in {"all", "h81"}:
            jobs.append(("H81", apply_h81_catalog_media(dry_run=dry_run)))

        for label, summary in jobs:
            for series_key, stats in sorted(summary["series"].items()):
                self.stdout.write(
                    f"{prefix}{series_key}: skus={stats['skus']} +{stats['created']} ~{stats['updated']}",
                )
            extra = ""
            if "unpublished_combined" in summary:
                extra = (
                    f" unpub_combined={summary['unpublished_combined']} unpub_static={summary['unpublished_static']}"
                )
            if "unpublished_legacy" in summary:
                extra += f" unpub_legacy={summary['unpublished_legacy']}"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{prefix}{label} diagrams: created={summary['created']} "
                    f"updated={summary['updated']} skipped={summary['skipped']}{extra}",
                ),
            )
