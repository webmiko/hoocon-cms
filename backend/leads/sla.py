"""SLA первого ответа на заявку — в рабочих часах расписания поддержки.

Сайт обещает клиенту ответ «в течение 2 рабочих часов»
(``leads.services._CLIENT_RESPONSE_TIME``). Дедлайн идёт по интервалам
``supportchat.SupportSchedule``: заявка, созданная вне рабочего времени,
добирает SLA со следующего открытого интервала (ночь и выходные не горят).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from django.utils import timezone

from leads.models import Lead

if TYPE_CHECKING:
    from django.db.models import QuerySet

# Срок первого ответа на новую заявку (совпадает с текстом письма клиенту).
LEAD_RESPONSE_SLA: timedelta = timedelta(hours=2)

# Safety bound while walking schedule intervals (misconfigured calendar).
_SEARCH_HORIZON_DAYS = 60


def _schedule_index() -> tuple[ZoneInfo, dict[int, Any]]:
    """Schedule TZ + ``{weekday: SupportScheduleDay}`` with prefetched intervals."""
    from supportchat.models import SupportScheduleDay
    from supportchat.schedule import ensure_default_schedule

    schedule = ensure_default_schedule()
    tz = ZoneInfo(schedule.timezone or "Europe/Moscow")
    days = {
        day.weekday: day for day in SupportScheduleDay.objects.filter(schedule=schedule).prefetch_related("intervals")
    }
    return tz, days


def lead_response_deadline(
    created_at: datetime,
    *,
    schedule_ctx: tuple[ZoneInfo, dict[int, Any]] | None = None,
) -> datetime | None:
    """Moment when the first-response SLA expires for a lead.

    Walks working intervals starting at ``created_at`` (schedule TZ) until
    ``LEAD_RESPONSE_SLA`` is fully consumed. Waiting between intervals and
    closed days does not burn the budget.

    Args:
        created_at: lead creation timestamp (aware).
        schedule_ctx: optional ``(tz, days)`` from :func:`_schedule_index`
            to reuse one schedule lookup across many leads.

    Returns:
        Aware deadline datetime, or None when no open interval exists within
        the search horizon (misconfiguration — treat as «not overdue»).
    """
    tz, days = schedule_ctx or _schedule_index()
    cursor = created_at.astimezone(tz)
    remaining = LEAD_RESPONSE_SLA
    for _ in range(_SEARCH_HORIZON_DAYS + 1):
        day = days.get(cursor.weekday())
        if day is not None and not day.is_closed:
            intervals = sorted(day.intervals.all(), key=lambda iv: iv.start_time)
            for interval in intervals:
                iv_start = datetime.combine(cursor.date(), interval.start_time, tzinfo=tz)
                iv_end = datetime.combine(cursor.date(), interval.end_time, tzinfo=tz)
                seg_start = max(cursor, iv_start)
                if seg_start >= iv_end:
                    continue
                available = iv_end - seg_start
                if available >= remaining:
                    return seg_start + remaining
                remaining -= available
                cursor = iv_end
        cursor = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=tz)
    return None


def overdue_new_leads(
    queryset: QuerySet[Lead],
    *,
    now: datetime | None = None,
) -> list[Lead]:
    """New leads whose first-response deadline has already passed.

    Args:
        queryset: base Lead queryset (already manager-scoped by the caller).
        now: reference moment (defaults to ``timezone.now()``).

    Returns:
        List of overdue leads, oldest first.
    """
    now = now or timezone.now()
    ctx = _schedule_index()
    overdue: list[Lead] = []
    qs = queryset.filter(status=Lead.LeadStatus.NEW).order_by("created_at", "pk")
    for lead in qs.iterator(chunk_size=200):
        deadline = lead_response_deadline(lead.created_at, schedule_ctx=ctx)
        if deadline is not None and deadline <= now:
            overdue.append(lead)
    return overdue
