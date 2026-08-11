"""Seed default support schedule (Mon–Thu 09–18, Fri 09–17, Sat–Sun closed)."""

from __future__ import annotations

from django.db import migrations


def seed_schedule(apps, schema_editor) -> None:
    SupportSchedule = apps.get_model("supportchat", "SupportSchedule")
    SupportScheduleDay = apps.get_model("supportchat", "SupportScheduleDay")
    SupportScheduleInterval = apps.get_model("supportchat", "SupportScheduleInterval")
    from datetime import time

    schedule, _ = SupportSchedule.objects.get_or_create(pk=1)
    defaults = {
        0: [(time(9, 0), time(18, 0))],
        1: [(time(9, 0), time(18, 0))],
        2: [(time(9, 0), time(18, 0))],
        3: [(time(9, 0), time(18, 0))],
        4: [(time(9, 0), time(17, 0))],
        5: None,
        6: None,
    }
    for weekday, intervals in defaults.items():
        day, created = SupportScheduleDay.objects.get_or_create(
            schedule=schedule,
            weekday=weekday,
            defaults={"is_closed": intervals is None},
        )
        if not created:
            continue
        if intervals is None:
            continue
        for start, end in intervals:
            SupportScheduleInterval.objects.create(
                day=day,
                start_time=start,
                end_time=end,
            )


def unseed(apps, schema_editor) -> None:
    SupportSchedule = apps.get_model("supportchat", "SupportSchedule")
    SupportSchedule.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("supportchat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_schedule, unseed),
    ]
