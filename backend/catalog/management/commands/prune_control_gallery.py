"""Unpublish A/AS ↔ D/DS sibling photos from the wrong edition card.

Usage::

    poetry run python manage.py prune_control_gallery
    poetry run python manage.py prune_control_gallery --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.control_gallery import prune_cross_control_images


class Command(BaseCommand):
    """Hide opposite-control marketing photos on dual-edition SKU cards."""

    help = "Unpublish A/AS↔D/DS sibling gallery photos on the wrong SKU."

    def add_arguments(self, parser: Any) -> None:
        """Register --dry-run."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count changes without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`prune_cross_control_images`."""
        dry_run = bool(options.get("dry_run"))
        summary = prune_cross_control_images(dry_run=dry_run)
        self.stdout.write(
            "Control gallery prune: "
            f"products={summary['products']} unpublished={summary['unpublished']} "
            f"dry_run={summary['dry_run']}",
        )
