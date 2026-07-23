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

from catalog.etl.manual_pdfs import (
    attach_dafu_manuals,
    attach_safu_manuals,
    default_manuals_dir,
    ensure_dafu_spring_category,
)


class Command(BaseCommand):
    """Link local DAFU/SAFU manuals to catalog SKUs; fix spring-return category."""

    help = "Attach DAFU/SAFU instruction PDFs and place DAFU products under spring-return."

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
            choices=("all", "dafu", "safu"),
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

        if not manuals_dir.is_dir():
            raise CommandError(f"Manuals directory not found: {manuals_dir}")

        prefix = "[dry-run] " if dry_run else ""
        summaries = []
        if series in {"all", "dafu"}:
            summaries.append(("DAFU", attach_dafu_manuals(manuals_dir, dry_run=dry_run)))
        if series in {"all", "safu"}:
            summaries.append(("SAFU", attach_safu_manuals(manuals_dir, dry_run=dry_run)))

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
