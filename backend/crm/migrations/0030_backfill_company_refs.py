"""Beat task: daily sweep — Company cards for clients with a label.

``ensure_company_ref`` lives in ``Client.save()`` — anything written in a
bypass (``update()``, imports, rows before the card feature) keeps
``company_ref`` empty forever. The sweep repairs the debt; its size is
also the dashboard warning count.
"""

from __future__ import annotations

from django.db import migrations


def _ensure_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Upsert daily 05:30 Europe/Moscow PeriodicTask."""
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="30",
        hour="5",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="Europe/Moscow",
    )
    PeriodicTask.objects.update_or_create(
        name="crm.backfill_company_refs",
        defaults={
            "task": "crm.backfill_company_refs",
            "crontab_id": schedule.pk,
            "interval_id": None,
            "solar_id": None,
            "clocked_id": None,
            "enabled": True,
            "description": (
                "Связывает контакты с заполненной «Компанией» и пустой "
                "карточкой юрлица — ловит записи в обход Client.save()."
            ),
        },
    )


def _disable_periodic(apps, schema_editor) -> None:  # noqa: ANN001, ARG001
    """Leave the row, turn the sweep off."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="crm.backfill_company_refs").update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0029_mailbox_intake"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(_ensure_periodic, _disable_periodic),
    ]
