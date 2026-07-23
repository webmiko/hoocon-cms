"""Backward-compatible alias — use ``attach_manual_diagrams``.

Usage::

    poetry run python manage.py attach_dafu_dimension_drawing
"""

from __future__ import annotations

from typing import Any

from catalog.management.commands.attach_manual_diagrams import Command as ManualDiagramsCommand


class Command(ManualDiagramsCommand):
    """Delegate to :class:`attach_manual_diagrams.Command`."""

    help = "Alias for attach_manual_diagrams (wiring + dimensions from PDFs)."

    def handle(self, *args: Any, **options: Any) -> None:
        """Forward to the manuals diagrams command."""
        self.stdout.write(
            self.style.NOTICE(
                "attach_dafu_dimension_drawing → attach_manual_diagrams",
            ),
        )
        super().handle(*args, **options)
