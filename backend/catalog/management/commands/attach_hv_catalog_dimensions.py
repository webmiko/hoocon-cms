"""Attach HV dimension drawings from the RU 2025 catalog PDF.

Usage::

    poetry run python manage.py attach_hv_catalog_dimensions
    poetry run python manage.py attach_hv_catalog_dimensions --dry-run
    poetry run python manage.py attach_hv_catalog_dimensions --pdf /path/to/catalog.pdf
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.hv_catalog_dimensions import apply_hv_catalog_dimensions, default_hv_ru_catalog_pdf


class Command(BaseCommand):
    """Replace HVA/HVD dimension gallery tiles with RU catalog crops."""

    help = "Crop and attach HV dimension drawings from 2025 каталог-2.2.3.pdf."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--pdf",
            type=str,
            default="",
            help="Override path to 2025 каталог-2.2.3.pdf.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        pdf_opt = str(options.get("pdf") or "").strip()
        catalog_pdf = Path(pdf_opt) if pdf_opt else default_hv_ru_catalog_pdf()
        summary = apply_hv_catalog_dimensions(dry_run=dry_run, catalog_pdf=catalog_pdf)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}attached={summary.get('attached', 0)} "
            f"created={summary['created']} updated={summary['updated']} "
            f"demoted={summary['demoted']} catalog={summary.get('catalog', '')}",
        )
        if summary.get("error"):
            self.stderr.write(str(summary["error"]))
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
