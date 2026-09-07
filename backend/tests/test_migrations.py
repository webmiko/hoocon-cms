"""Regression test for pending migrations (model/migration drift)."""

from django.core.management import call_command
from django.test import TestCase


class MigrationsCheckTest(TestCase):
    def test_no_pending_migrations(self) -> None:
        """Models and migrations must stay in sync.

        Catches help-text/default/index drift that ``makemigrations --check``
        would flag before it reaches CI or another developer's checkout.
        """
        call_command("makemigrations", "--check", "--dry-run")
