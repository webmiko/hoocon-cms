"""Working-hours helpers for support chat."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from supportchat.models import SupportSchedule, SupportScheduleDay, SupportScheduleInterval

# Default intervals from plan §2.4.
_DEFAULT_WEEKDAY_INTERVALS: dict[int, list[tuple[time, time]] | None] = {
    0: [(time(9, 0), time(18, 0))],  # Mon
    1: [(time(9, 0), time(18, 0))],
    2: [(time(9, 0), time(18, 0))],
    3: [(time(9, 0), time(18, 0))],
    4: [(time(9, 0), time(17, 0))],  # Fri
    5: None,  # Sat closed
    6: None,  # Sun closed
}


def ensure_default_schedule() -> SupportSchedule:
    """Create singleton schedule + 7 days with plan defaults if missing."""
    schedule = SupportSchedule.load()
    for weekday, intervals in _DEFAULT_WEEKDAY_INTERVALS.items():
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
    return schedule


def _local_now(at: datetime | None, tz_name: str) -> datetime:
    """Normalize ``at`` (or now) to timezone-aware local datetime."""
    tz = ZoneInfo(tz_name)
    if at is None:
        return timezone.now().astimezone(tz)
    if timezone.is_naive(at):
        return timezone.make_aware(at, tz)
    return at.astimezone(tz)


def is_open_now(
    at: datetime | None = None,
    *,
    schedule: SupportSchedule | None = None,
) -> bool:
    """True when support is within a configured open interval."""
    sched = schedule or ensure_default_schedule()
    local = _local_now(at, sched.timezone or "Europe/Moscow")
    day = (
        SupportScheduleDay.objects.filter(schedule=sched, weekday=local.weekday())
        .prefetch_related("intervals")
        .first()
    )
    if day is None or day.is_closed:
        return False
    clock = local.timetz().replace(tzinfo=None)
    for interval in day.intervals.all():
        if interval.start_time <= clock < interval.end_time:
            return True
    return False


def next_open_at(
    at: datetime | None = None,
    *,
    schedule: SupportSchedule | None = None,
    horizon_days: int = 14,
) -> datetime | None:
    """Next datetime when support opens (local TZ, returned aware)."""
    sched = schedule or ensure_default_schedule()
    local = _local_now(at, sched.timezone or "Europe/Moscow")
    if is_open_now(local, schedule=sched):
        return local

    days = {
        d.weekday: d
        for d in SupportScheduleDay.objects.filter(schedule=sched).prefetch_related(
            "intervals",
        )
    }
    for offset in range(horizon_days + 1):
        candidate_date = (local + timedelta(days=offset)).date()
        day = days.get(candidate_date.weekday())
        if day is None or day.is_closed:
            continue
        intervals = list(day.intervals.all())
        if not intervals:
            continue
        for interval in intervals:
            start_dt = datetime.combine(
                candidate_date,
                interval.start_time,
                tzinfo=ZoneInfo(sched.timezone or "Europe/Moscow"),
            )
            if start_dt > local:
                return start_dt
    return None


def schedule_public_payload(
    *,
    schedule: SupportSchedule | None = None,
    at: datetime | None = None,
) -> dict[str, object]:
    """Public JSON for widget (no PII)."""
    sched = schedule or ensure_default_schedule()
    open_now = is_open_now(at, schedule=sched)
    nxt = next_open_at(at, schedule=sched)
    days_out: list[dict[str, object]] = []
    for day in SupportScheduleDay.objects.filter(schedule=sched).prefetch_related("intervals").order_by("weekday"):
        days_out.append(
            {
                "weekday": day.weekday,
                "is_closed": day.is_closed,
                "intervals": [
                    {
                        "start": iv.start_time.strftime("%H:%M"),
                        "end": iv.end_time.strftime("%H:%M"),
                    }
                    for iv in day.intervals.all()
                ],
            },
        )
    return {
        "timezone": sched.timezone,
        "is_open_now": open_now,
        "next_open_at": nxt.isoformat() if nxt else None,
        "auto_reply_outside_hours": sched.auto_reply_outside_hours,
        "days": days_out,
    }
