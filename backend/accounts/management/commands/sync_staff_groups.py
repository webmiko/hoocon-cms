"""Create/update staff Groups: Админ, Менеджер, Аналитик.

Usage::

    poetry run python manage.py sync_staff_groups
    poetry run python manage.py sync_staff_groups --dry-run
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from accounts.services import ensure_staff_groups


class Command(BaseCommand):
    """Idempotent sync of staff role Groups and permissions."""

    help = "Sync Groups Админ / Менеджер / Аналитик and their permissions."

    def add_arguments(self, parser: Any) -> None:
        """Register CLI flags."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run :func:`ensure_staff_groups` and print a short summary."""
        dry_run = bool(options.get("dry_run"))
        summary = ensure_staff_groups(dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        for name, stats in summary["groups"].items():
            self.stdout.write(
                f"{prefix}{name}: +{stats['added']} -{stats['removed']} kept={stats['kept']} total={stats['total']}",
            )
        self.stdout.write(self.style.SUCCESS(f"{prefix}Staff groups synced."))
