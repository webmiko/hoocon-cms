"""Attach series-8100 brass PDF datasheet to ``8100-bv*`` SKUs.

Usage::

    poetry run python manage.py attach_8100_catalog_media
    poetry run python manage.py attach_8100_catalog_media --dry-run
    poetry run python manage.py attach_8100_catalog_media --pdf /path/to.pdf
    poetry run python manage.py attach_8100_catalog_media --force-attrs

Diagram page-crops are not attached to the gallery (look in the PDF).
Re-running unpublishes any legacy ``8100-series/*`` tiles.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.ball_valve_8100_catalog_media import apply_8100_catalog_media


class Command(BaseCommand):
    """Attach 8100 series instruction PDF to brass body SKUs."""

    help = "Attach series-8100 PDF instruction to brass SKUs (no gallery crops)."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument("--dry-run", action="store_true", help="Count only.")
        parser.add_argument(
            "--pdf",
            type=str,
            default="",
            help="Override path to шаровые краны серии 8100.pdf.",
        )
        parser.add_argument(
            "--force-attrs",
            action="store_true",
            help="Overwrite size attrs when they disagree with the PDF table.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run attach."""
        dry_run = bool(options["dry_run"])
        pdf_opt = str(options.get("pdf") or "").strip()
        pdf_path = Path(pdf_opt) if pdf_opt else None
        summary = apply_8100_catalog_media(
            dry_run=dry_run,
            pdf_path=pdf_path,
            force_attrs=bool(options["force_attrs"]),
        )
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}pdf create={summary['pdf_created']} update={summary['pdf_updated']} "
            f"attrs_filled={summary['attrs_filled']} "
            f"attrs_mismatch={summary['attrs_mismatched']} "
            f"unpublished_diagrams={summary['unpublished_diagrams']} "
            f"pdf={summary['pdf']}",
        )
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
