"""Celery tasks for accounts app (staff messenger alerts)."""

from __future__ import annotations

# Re-export so Celery autodiscovers ``accounts.tasks``.
from accounts.max_tasks import (  # noqa: F401
    notify_staff_max_new_lead,
    notify_staff_max_support,
)
from accounts.telegram_tasks import send_ops_telegram_alert_task  # noqa: F401
from accounts.vk_tasks import (  # noqa: F401
    notify_staff_vk_new_lead,
    notify_staff_vk_support,
    notify_superuser_vk_crm,
    retire_vk_support_alert,
)
