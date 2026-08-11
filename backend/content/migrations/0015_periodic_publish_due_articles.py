"""Periodic beat: publish due scheduled articles (news + social)."""

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
        name="content.publish_due_articles",
        defaults={
            "task": "content.publish_due_articles",
            "interval_id": schedule.pk,
            "crontab_id": None,
            "solar_id": None,
            "clocked_id": None,
            "enabled": True,
            "description": (
                "Go-live: новость о статье + анонс в соцсети "
                "(tipy / pitanie / MU-HV / analog-belimo)."
            ),
        },
    )


def _disable_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Disable the task on reverse (keep row for audit)."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="content.publish_due_articles").update(
        enabled=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0014_articles_guides_and_news"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(_ensure_periodic, _disable_periodic),
    ]
