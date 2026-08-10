"""Report missing weight / cable / wire attrs on DA / SA / HV SKUs.

Usage::

    poetry run python manage.py audit_series_attr_gaps
    poetry run python manage.py audit_series_attr_gaps --slugs weight,cable-length
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.series_attr_gaps import (
    DEFAULT_ATTR_SLUGS,
    build_series_attr_gap_report,
    format_series_attr_gap_report,
)


class Command(BaseCommand):
    """Print ETL attribute coverage gaps for DA/SA/HV families."""

    help = "Audit published DA/SA/HV SKUs for missing ТТХ attribute slugs."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--slugs",
            default=",".join(DEFAULT_ATTR_SLUGS),
            help=f"Comma-separated attribute slugs (default: {','.join(DEFAULT_ATTR_SLUGS)}).",
        )
        parser.add_argument(
            "--include-unpublished",
            action="store_true",
            help="Include unpublished SKUs.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Build and print the gap report."""
        raw = str(options["slugs"] or "")
        slugs = [part.strip() for part in raw.split(",") if part.strip()]
        report = build_series_attr_gap_report(
            attr_slugs=slugs or DEFAULT_ATTR_SLUGS,
            published_only=not bool(options["include_unpublished"]),
        )
        self.stdout.write(format_series_attr_gap_report(report))
        gap_count = len(report.model_gaps)
        if gap_count:
            self.stdout.write(self.style.WARNING(f"\nModels with gaps: {gap_count}"))
        else:
            self.stdout.write(self.style.SUCCESS("\nNo gaps for selected slugs."))
