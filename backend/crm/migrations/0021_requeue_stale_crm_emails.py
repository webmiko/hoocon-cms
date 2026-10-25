"""Beat task: requeue outbound CRM mail stuck in QUEUED.

Independent of IMAP fetch. Disabling inbound mail must not disable the watchdog.
"""

from __future__ import annotations

from django.db import migrations


def _ensure_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert IntervalSchedule + PeriodicTask every 15 minutes."""
    interval_schedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _created = interval_schedule.objects.get_or_create(every=15, period="minutes")
    periodic_task.objects.update_or_create(
        name="crm.requeue_stale_crm_emails",
        defaults={
            "task": "crm.requeue_stale_crm_emails",
            "interval_id": schedule.pk,
            "crontab_id": None,
            "solar_id": None,
            "clocked_id": None,
            "enabled": True,
            "description": "Повторно ставит в очередь исходящие письма, зависшие в статусе «в очереди».",
        },
    )


def _disable_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Leave the row, turn the watchdog off."""
    periodic_task = apps.get_model("django_celery_beat", "PeriodicTask")
    periodic_task.objects.filter(name="crm.requeue_stale_crm_emails").update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0020_plannedtouch_status"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(_ensure_periodic, _disable_periodic),
    ]
