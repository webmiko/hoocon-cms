"""Unpublish SA DS/DST sibling photos from the wrong edition card.

Usage::

    poetry run python manage.py prune_sa_gallery
    poetry run python manage.py prune_sa_gallery --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.sa_gallery import prune_sa_cross_edition_images


class Command(BaseCommand):
    """Hide opposite-edition photos on SA fire/smoke SKU cards."""

    help = "Unpublish SA DS↔DST sibling gallery photos on the wrong SKU."

    def add_arguments(self, parser: Any) -> None:
        """Register --dry-run."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count changes without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`prune_sa_cross_edition_images`."""
        dry_run = bool(options.get("dry_run"))
        summary = prune_sa_cross_edition_images(dry_run=dry_run)
        self.stdout.write(
            "SA gallery prune: "
            f"products={summary['products']} unpublished={summary['unpublished']} "
            f"dry_run={summary['dry_run']}",
        )
