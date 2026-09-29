"""Periodic beat: support-chat housekeeping sweep every 15 minutes."""

from __future__ import annotations

from django.db import migrations


def _ensure_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert IntervalSchedule + PeriodicTask every 15 minutes."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = IntervalSchedule.objects.get_or_create(
        every=15,
        period="minutes",
    )
    PeriodicTask.objects.update_or_create(
        name="supportchat.housekeeping",
        defaults={
            "task": "supportchat.housekeeping",
            "interval_id": schedule.pk,
            "crontab_id": None,
            "solar_id": None,
            "clocked_id": None,
            "enabled": True,
            "description": (
                "Чат поддержки: резерв busy-followup, авто-закрытие "
                "неактивных диалогов, чистка пустых сессий."
            ),
        },
    )


def _disable_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Disable the task on reverse (keep row for audit)."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="supportchat.housekeeping").update(
        enabled=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("supportchat", "0011_faq_show_on_home_help_text_ru"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(_ensure_periodic, _disable_periodic),
    ]
