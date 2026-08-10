"""Normalize Product.instructions layout to the DAFU instruction-tab style.

Usage::

    poetry run python manage.py normalize_instruction_style
    poetry run python manage.py normalize_instruction_style --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from catalog.etl.instruction_style import apply_instruction_style


class Command(BaseCommand):
    """Rewrite install guides: chapters, blank lines, typos, glossary."""

    help = "Normalize Product.instructions to DAFU-style chapters / lists."

    def add_arguments(self, parser: Any) -> None:
        """Register --dry-run."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count changes without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`apply_instruction_style` and print a short summary."""
        dry_run = bool(options.get("dry_run"))
        summary = apply_instruction_style(dry_run=dry_run)
        self.stdout.write(
            "instruction style: "
            f"checked={summary['checked']} updated={summary['updated']} "
            f"unchanged={summary['unchanged']} dry_run={summary['dry_run']}",
        )
        for slug in summary.get("samples") or []:
            self.stdout.write(f"  sample: {slug}")
