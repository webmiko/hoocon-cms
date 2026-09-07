"""Celery tasks for accounts app (staff Telegram alerts)."""

from __future__ import annotations

# Re-export so Celery autodiscovers ``accounts.tasks``.
from accounts.telegram_tasks import (  # noqa: F401
    notify_staff_telegram_new_lead,
    notify_staff_telegram_support,
    notify_superuser_telegram_crm,
)
