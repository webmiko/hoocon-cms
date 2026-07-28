"""Attach instruction PDFs from ``_инструкции-pdf`` to matching SKUs.

Usage::

    poetry run python manage.py attach_manual_pdfs
    poetry run python manage.py attach_manual_pdfs --dry-run
    poetry run python manage.py attach_manual_pdfs --dir /path/to/pdfs
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from catalog.etl.h81_catalog_media import apply_h81_instruction_pdfs
from catalog.etl.manual_pdfs import (
    attach_dafu_manuals,
    attach_damqu_manuals,
    attach_damu_manuals,
    attach_hva_manuals,
    attach_hvd_manuals,
    attach_safu_manuals,
    attach_samu_manuals,
    default_manuals_dir,
    ensure_dafu_spring_category,
)


class Command(BaseCommand):
    """Link local DAFU/SAFU/DAMU manuals to catalog SKUs; fix spring-return category."""

    help = "Attach DAFU/SAFU/DAMU/DAMQU instruction PDFs; place DAFU under spring-return."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dir",
            type=str,
            default="",
            help="Manuals directory (default: repo _инструкции-pdf).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show plan without writing.",
        )
        parser.add_argument(
            "--skip-category",
            action="store_true",
            help="Do not move DAFU products to spring-return category.",
        )
        parser.add_argument(
            "--series",
            choices=("all", "dafu", "safu", "damu", "damqu", "samu", "hvd", "hva", "h81"),
            default="all",
            help="Which series manuals to attach (default: all).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run category alignment then PDF attach."""
        dry_run = bool(options["dry_run"])
        series = str(options.get("series") or "all")
        raw_dir = (options.get("dir") or "").strip()
        manuals_dir = Path(raw_dir).expanduser().resolve() if raw_dir else default_manuals_dir()

        if series in {"all", "dafu"} and not options["skip_category"]:
            cat = ensure_dafu_spring_category(dry_run=dry_run)
            prefix = "[dry-run] " if dry_run else ""
            self.stdout.write(
                f"{prefix}DAFU category → {cat['category']}: moved={cat['moved']} already={cat['already']}",
            )

        if series != "h81" and not manuals_dir.is_dir():
            raise CommandError(f"Manuals directory not found: {manuals_dir}")

        prefix = "[dry-run] " if dry_run else ""
        summaries: list[tuple[str, dict[str, Any]]] = []
        if series in {"all", "dafu"}:
            summaries.append(("DAFU", attach_dafu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "safu"}:
            summaries.append(("SAFU", attach_safu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "damu"}:
            summaries.append(("DAMU", attach_damu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "damqu"}:
            summaries.append(("DAMQU", attach_damqu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "samu"}:
            summaries.append(("SAMU", attach_samu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "hvd"}:
            summaries.append(("HVD", attach_hvd_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "hva"}:
            summaries.append(("HVA", attach_hva_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "h81"}:
            h81 = apply_h81_instruction_pdfs(dry_run=dry_run)
            self.stdout.write(
                f"{prefix}H81 instructions created={h81['created']} updated={h81['updated']} skipped={h81['skipped']}",
            )
            for pair, stats in sorted(h81["by_pair"].items()):
                self.stdout.write(
                    f"  {pair}: skus={stats['skus']} +{stats['created']} ~{stats['updated']} skip={stats['skipped']}",
                )
            for warn in h81["warnings"]:
                self.stdout.write(self.style.WARNING(f"  ! {warn}"))

        for label, summary in summaries:
            self.stdout.write(
                f"{prefix}{label} manuals={summary['manuals']} "
                f"created={summary['created']} updated={summary['updated']} "
                f"skipped={summary['skipped']}",
            )
            for code, titles in sorted(summary["by_sku"].items()):
                self.stdout.write(f"  {code}: {', '.join(titles)}")
            for warn in summary["warnings"]:
                self.stdout.write(self.style.WARNING(f"  ! {warn}"))
        self.stdout.write(self.style.SUCCESS(f"{prefix}Manual PDFs synced."))
