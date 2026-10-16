"""Sales-manager performance report for the head of sales (РОП)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone

from accounts.roles import GROUP_MANAGER, staff_sees_all_leads
from cabinet.models import Order
from crm.models import (
    Activity,
    Call,
    CallDirection,
    CallState,
    Client,
    EmailMessage,
    EmailStatus,
    Quote,
    QuoteStatus,
)
from leads.models import Lead
from leads.services import manager_display_name

User = get_user_model()

_MOSCOW: ZoneInfo = ZoneInfo("Europe/Moscow")
_SERIES_WEEKS: int = 12


def _metric(rows: dict[Any, Any], key_id: int, field: str) -> int:
    """Read one annotated counter; missing manager or field is zero."""
    raw = rows.get(key_id)
    if raw is None:
        return 0
    bucket = cast("dict[str, int]", raw)
    return int(bucket.get(field, 0))


def _metric_seconds(rows: dict[Any, Any], key_id: int, field: str) -> int | None:
    """Average talk time in whole seconds; missing calls stay empty."""
    raw = rows.get(key_id)
    if raw is None:
        return None
    bucket = cast("dict[str, Any]", raw)
    value = bucket.get(field)
    if value is None:
        return None
    return int(round(float(value)))


def _pct(part: int, whole: int) -> int | None:
    """Integer percent. Empty denominator is unknown, not zero."""
    if whole <= 0:
        return None
    return int(round(100 * part / whole))


def _pct_label(value: int | None) -> str:
    """``42%`` or an em dash when the cohort is empty."""
    if value is None:
        return "—"
    return f"{value}%"


def _talk_label(seconds: int | None) -> str:
    """Short duration for a card: seconds under a minute, else minutes."""
    if seconds is None:
        return "—"
    if seconds < 60:
        return f"{seconds} с"
    minutes, rest = divmod(seconds, 60)
    if rest == 0:
        return f"{minutes} мин"
    return f"{minutes} мин {rest} с"


def _touch_label(minutes: int | None) -> str:
    """Median first-touch lag: minutes under an hour, else hours."""
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    if rest == 0:
        return f"{hours} ч"
    return f"{hours} ч {rest} мин"


def _median_minutes(samples: list[float]) -> int | None:
    """Median of positive lags in minutes. Empty sample is unknown."""
    if not samples:
        return None
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        value = ordered[mid]
    else:
        value = (ordered[mid - 1] + ordered[mid]) / 2
    return int(round(value))


def _earliest_touch(
    created: datetime,
    processed: datetime | None,
    call_at: datetime | None,
    activity_at: datetime | None,
) -> datetime | None:
    """First customer touch at or after the lead was created.

    A touch is a linked call, a CRM activity written by a person, or closing
    the lead. The automatic «Входящая заявка» note has no author and does
    not count. Opening the card (``seen_at``) does not count either.
    """
    moments = [item for item in (processed, call_at, activity_at) if item is not None and item >= created]
    if not moments:
        return None
    return min(moments)


def _series_starts(since: datetime | None, until: datetime, grain: str) -> list[datetime]:
    """Bucket starts in Europe/Moscow. Weeks are Mondays, twelve of them."""
    until_local = timezone.localtime(until, _MOSCOW)
    if grain == "week":
        this_monday = (until_local - timedelta(days=until_local.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        start = this_monday - timedelta(weeks=_SERIES_WEEKS - 1)
        return [start + timedelta(weeks=index) for index in range(_SERIES_WEEKS)]
    if since is None:
        return _series_starts(since, until, "week")
    start = timezone.localtime(since, _MOSCOW).replace(hour=0, minute=0, second=0, microsecond=0)
    count = (until_local.date() - start.date()).days + 1
    if count < 1:
        count = 1
    if count > 31:
        count = 31
        start = until_local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)
    return [start + timedelta(days=index) for index in range(count)]


def _bucket_index(moment: datetime, starts: list[datetime], grain: str) -> int | None:
    """Index of ``moment`` in ``starts``, or None when it falls outside."""
    local = timezone.localtime(moment, _MOSCOW)
    if grain == "week":
        monday = (local - timedelta(days=local.weekday())).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        index = (monday - starts[0]).days // 7
    else:
        index = (local.date() - starts[0].date()).days
    if index < 0 or index >= len(starts):
        return None
    return index


def _build_series(
    *,
    leads: QuerySet[Any],
    calls: QuerySet[Any],
    quotes: QuerySet[Any],
    since: datetime | None,
    until: datetime,
    grain: str,
    call_talk: Q,
    call_missed: Q,
) -> dict[str, Any]:
    """Daily or weekly counts so a quiet day is a gap, not one period total."""
    starts = _series_starts(since, until, grain)
    lower = starts[0]
    if since is not None and since > lower:
        lower = since
    buckets: list[dict[str, Any]] = [
        {
            "label": f"{item.day:02d}.{item.month:02d}",
            "leads_new": 0,
            "calls_talked": 0,
            "calls_missed": 0,
            "quotes_sent": 0,
        }
        for item in starts
    ]

    def _add(moments: Any, field: str) -> None:
        for moment in moments:
            if moment is None:
                continue
            index = _bucket_index(moment, starts, grain)
            if index is None:
                continue
            buckets[index][field] += 1

    _add(
        leads.filter(created_at__gte=lower, created_at__lt=until).values_list("created_at", flat=True),
        "leads_new",
    )
    _add(
        calls.filter(call_talk, started_at__gte=lower, started_at__lt=until).values_list("started_at", flat=True),
        "calls_talked",
    )
    _add(
        calls.filter(call_missed, started_at__gte=lower, started_at__lt=until).values_list("started_at", flat=True),
        "calls_missed",
    )
    _add(
        quotes.filter(sent_at__isnull=False, sent_at__gte=lower, sent_at__lt=until).values_list("sent_at", flat=True),
        "quotes_sent",
    )
    peak = 0
    for bucket in buckets:
        peak = max(peak, int(bucket["leads_new"]), int(bucket["calls_missed"]))
    for bucket in buckets:
        leads_new = int(bucket["leads_new"])
        missed = int(bucket["calls_missed"])
        bucket["leads_pct"] = 0 if peak == 0 else int(round(100 * leads_new / peak))
        bucket["missed_pct"] = 0 if peak == 0 else int(round(100 * missed / peak))
    if grain == "week":
        caption = "Новые заявки и пропущенные за последние 12 недель"
    else:
        caption = "Новые заявки и пропущенные по дням"
    return {"grain": grain, "caption": caption, "buckets": buckets}


def build_sales_report(
    *,
    since: datetime | None,
    until: datetime | None = None,
    user: Any | None = None,
    manager_id: int | None = None,
) -> dict[str, Any]:
    """Per-manager funnel, call quality, and cohort conversion for a period.

    Head of sales (``staff_sees_all_leads``) sees every manager; a scoped
    manager gets a single own row even if ``manager_id`` points at someone
    else. An unscoped viewer may pass ``manager_id`` to open one card.

    Cohort rates use leads created in the period (by assignee). A sent quote
    or an order counts when it is linked to that lead, whoever created it.
    First touch is the median lag until a call, an activity, or closing.
    A missed call is an inbound one that already ended with no talk time.

    Args:
        since: inclusive lower bound (None = all time).
        until: exclusive upper bound (None = now).
        user: viewer; None = unscoped (Celery mail).
        manager_id: one manager card for an unscoped viewer.

    Returns:
        ``totals``, ``managers``, ``series``, ``focus``, period bounds.
    """
    until = until or timezone.now()
    scoped = user is not None and not staff_sees_all_leads(user)
    focus_user = None
    if scoped and user is not None:
        focus_id: int | None = user.pk
    elif manager_id is not None:
        focus_user = User.objects.filter(pk=manager_id).first()
        focus_id = focus_user.pk if focus_user is not None else None
    else:
        focus_id = None

    lead_created = Q()
    lead_done = Q(status=Lead.LeadStatus.DONE)
    quote_created = Q()
    # Issued once = sent_at stamped; accepted/rejected КП were sent too.
    quote_sent = Q(sent_at__isnull=False)
    quote_accepted = Q(status=QuoteStatus.ACCEPTED)
    order_created = Q()
    email_sent = Q(status=EmailStatus.SENT)
    call_period = Q(started_at__lt=until)
    if since is not None:
        call_period &= Q(started_at__gte=since)
    call_talk = call_period & Q(talk_duration__gt=0)
    call_inbound_talk = call_talk & Q(direction=CallDirection.INBOUND)
    call_outbound_talk = call_talk & Q(direction=CallDirection.OUTBOUND)
    call_missed = call_period & Q(
        direction=CallDirection.INBOUND,
        talk_duration=0,
        state=CallState.DISCONNECTED,
    )
    call_unlinked = call_period & Q(client__isnull=True, lead__isnull=True)
    activity_created = Q()
    if since is not None:
        lead_created &= Q(created_at__gte=since)
        lead_done &= Q(processed_at__gte=since)
        quote_created &= Q(created_at__gte=since)
        quote_sent &= Q(sent_at__gte=since)
        quote_accepted &= Q(updated_at__gte=since)
        order_created &= Q(created_at__gte=since)
        email_sent &= Q(sent_at__gte=since)
        activity_created &= Q(created_at__gte=since)
    lead_created &= Q(created_at__lt=until)
    lead_done &= Q(processed_at__lt=until)
    quote_created &= Q(created_at__lt=until)
    quote_sent &= Q(sent_at__lt=until)
    quote_accepted &= Q(updated_at__lt=until)
    order_created &= Q(created_at__lt=until)
    email_sent &= Q(sent_at__lt=until)
    activity_created &= Q(created_at__lt=until)

    leads = Lead.objects.all()
    quotes = Quote.objects.all()
    orders = Order.objects.all()
    emails = EmailMessage.objects.all()
    calls = Call.objects.all()
    activities = Activity.objects.all()
    clients = Client.objects.filter(is_active=True)
    if focus_id is not None:
        leads = leads.filter(Q(assignee_id=focus_id) | Q(processed_by_id=focus_id))
        quotes = quotes.filter(created_by_id=focus_id)
        emails = emails.filter(created_by_id=focus_id)
        calls = calls.filter(manager_id=focus_id)
        activities = activities.filter(author_id=focus_id)
        clients = clients.filter(assignee_id=focus_id)
        orders = orders.filter(quote__created_by_id=focus_id)

    overdue_next = clients.filter(
        next_contact_at__isnull=False,
        next_contact_at__lt=until,
    ).count()

    totals: dict[str, Any] = {
        "leads_new": leads.filter(lead_created).count(),
        "leads_done": leads.filter(lead_done).count(),
        "quotes_created": quotes.filter(quote_created).count(),
        "quotes_sent": quotes.filter(quote_sent).count(),
        "quotes_accepted": quotes.filter(quote_accepted).count(),
        "orders_created": orders.filter(order_created).count(),
        "emails_sent": emails.filter(email_sent).count(),
        "calls_talked": calls.filter(call_talk).count(),
        "calls_inbound_talked": calls.filter(call_inbound_talk).count(),
        "calls_outbound_talked": calls.filter(call_outbound_talk).count(),
        "calls_missed": calls.filter(call_missed).count(),
        "calls_unlinked": calls.filter(call_unlinked).count(),
        "activities": activities.filter(activity_created).count(),
        "overdue_next_contact": overdue_next,
        "open_quotes": quotes.filter(
            status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT),
        ).count(),
    }
    avg_talk_raw = calls.filter(call_talk).aggregate(avg_talk=Avg("talk_duration"))["avg_talk"]
    totals["avg_talk_seconds"] = None if avg_talk_raw is None else int(round(float(avg_talk_raw)))
    totals["avg_talk_label"] = _talk_label(totals["avg_talk_seconds"])

    lead_rows = {
        row["assignee_id"]: row
        for row in leads.exclude(assignee_id=None)
        .values("assignee_id")
        .annotate(
            leads_new=Count("id", filter=lead_created),
            leads_done=Count("id", filter=lead_done),
        )
    }
    quote_rows = {
        row["created_by_id"]: row
        for row in quotes.exclude(created_by_id=None)
        .values("created_by_id")
        .annotate(
            quotes_created=Count("id", filter=quote_created),
            quotes_sent=Count("id", filter=quote_sent),
            quotes_accepted=Count("id", filter=quote_accepted),
            open_quotes=Count(
                "id",
                filter=Q(status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT)),
            ),
        )
    }
    order_rows = {
        row["quote__created_by_id"]: row
        for row in orders.exclude(quote__created_by_id=None)
        .values("quote__created_by_id")
        .annotate(orders_created=Count("id", filter=order_created))
    }
    email_rows = {
        row["created_by_id"]: row
        for row in emails.exclude(created_by_id=None)
        .values("created_by_id")
        .annotate(emails_sent=Count("id", filter=email_sent))
    }
    call_rows = {
        row["manager_id"]: row
        for row in calls.exclude(manager_id=None)
        .values("manager_id")
        .annotate(
            calls_talked=Count("id", filter=call_talk),
            calls_inbound_talked=Count("id", filter=call_inbound_talk),
            calls_outbound_talked=Count("id", filter=call_outbound_talk),
            calls_missed=Count("id", filter=call_missed),
            calls_unlinked=Count("id", filter=call_unlinked),
            avg_talk=Avg("talk_duration", filter=call_talk),
        )
    }
    activity_rows = {
        row["author_id"]: row
        for row in activities.exclude(author_id=None)
        .values("author_id")
        .annotate(activities=Count("id", filter=activity_created))
    }
    overdue_rows = {
        row["assignee_id"]: row["n"]
        for row in clients.exclude(assignee_id=None)
        .filter(next_contact_at__isnull=False, next_contact_at__lt=until)
        .values("assignee_id")
        .annotate(n=Count("id"))
    }

    staff_ids: set[int] = set()
    staff_ids.update(k for k in lead_rows if k)
    staff_ids.update(k for k in quote_rows if k)
    staff_ids.update(k for k in order_rows if k)
    staff_ids.update(k for k in email_rows if k)
    staff_ids.update(k for k in call_rows if k)
    staff_ids.update(k for k in activity_rows if k)
    staff_ids.update(k for k in overdue_rows if k)
    if focus_id is not None:
        staff_ids.add(focus_id)
    else:
        group_ids = User.objects.filter(
            is_staff=True,
            groups__name=GROUP_MANAGER,
        ).values_list("pk", flat=True)
        staff_ids.update(group_ids)

    cohort = list(
        leads.filter(lead_created).values_list("id", "assignee_id", "created_at", "processed_at"),
    )
    cohort_ids = [row[0] for row in cohort]
    call_times: dict[int, list[datetime]] = {}
    for lead_pk, started in Call.objects.filter(
        lead_id__in=cohort_ids,
        started_at__isnull=False,
    ).values_list("lead_id", "started_at"):
        call_times.setdefault(lead_pk, []).append(started)
    activity_times: dict[int, list[datetime]] = {}
    for lead_pk, happened in Activity.objects.filter(
        lead_id__in=cohort_ids,
        author__isnull=False,
    ).values_list(
        "lead_id",
        "created_at",
    ):
        activity_times.setdefault(lead_pk, []).append(happened)
    sent_lead_ids = set(
        Quote.objects.filter(lead_id__in=cohort_ids, sent_at__isnull=False).values_list("lead_id", flat=True),
    )
    order_lead_ids = set(
        Order.objects.filter(quote__lead_id__in=cohort_ids).values_list("quote__lead_id", flat=True),
    )
    touch_by_user: dict[int | None, list[float]] = {}
    untouched_by_user: dict[int | None, int] = {}
    cohort_by_user: dict[int | None, int] = {}
    sent_by_user: dict[int | None, int] = {}
    order_by_user: dict[int | None, int] = {}
    for lead_id, assignee_id, created_at, processed_at in cohort:
        cohort_by_user[assignee_id] = cohort_by_user.get(assignee_id, 0) + 1
        if lead_id in sent_lead_ids:
            sent_by_user[assignee_id] = sent_by_user.get(assignee_id, 0) + 1
        if lead_id in order_lead_ids:
            order_by_user[assignee_id] = order_by_user.get(assignee_id, 0) + 1
        valid_calls = [item for item in call_times.get(lead_id, []) if item >= created_at]
        valid_activities = [item for item in activity_times.get(lead_id, []) if item >= created_at]
        touched = _earliest_touch(
            created_at,
            processed_at,
            min(valid_calls) if valid_calls else None,
            min(valid_activities) if valid_activities else None,
        )
        if touched is None:
            untouched_by_user[assignee_id] = untouched_by_user.get(assignee_id, 0) + 1
            continue
        lag_minutes = (touched - created_at).total_seconds() / 60
        touch_by_user.setdefault(assignee_id, []).append(lag_minutes)

    def _kpi(owner_id: int | None, *, everyone: bool) -> dict[str, Any]:
        if everyone:
            samples = [item for group in touch_by_user.values() for item in group]
            whole = len(cohort)
            sent = len(sent_lead_ids)
            ordered = len(order_lead_ids)
            untouched = sum(untouched_by_user.values())
        else:
            samples = touch_by_user.get(owner_id, [])
            whole = cohort_by_user.get(owner_id, 0)
            sent = sent_by_user.get(owner_id, 0)
            ordered = order_by_user.get(owner_id, 0)
            untouched = untouched_by_user.get(owner_id, 0)
        quote_pct = _pct(sent, whole)
        order_pct = _pct(ordered, whole)
        touch_minutes = _median_minutes(samples)
        return {
            "leads_untouched": untouched,
            "first_touch_minutes": touch_minutes,
            "first_touch_label": _touch_label(touch_minutes),
            "cohort_quote_pct": quote_pct,
            "cohort_quote_label": _pct_label(quote_pct),
            "cohort_order_pct": order_pct,
            "cohort_order_label": _pct_label(order_pct),
        }

    totals.update(_kpi(None, everyone=True))

    managers: list[dict[str, Any]] = []
    users = User.objects.filter(pk__in=staff_ids).order_by("first_name", "username")
    for staff in users:
        pk = staff.pk
        avg_talk_seconds = _metric_seconds(call_rows, pk, "avg_talk")
        managers.append(
            {
                "user_id": pk,
                "username": staff.get_username(),
                "display_name": manager_display_name(staff),
                "leads_new": _metric(lead_rows, pk, "leads_new"),
                "leads_done": _metric(lead_rows, pk, "leads_done"),
                "quotes_created": _metric(quote_rows, pk, "quotes_created"),
                "quotes_sent": _metric(quote_rows, pk, "quotes_sent"),
                "quotes_accepted": _metric(quote_rows, pk, "quotes_accepted"),
                "open_quotes": _metric(quote_rows, pk, "open_quotes"),
                "orders_created": _metric(order_rows, pk, "orders_created"),
                "emails_sent": _metric(email_rows, pk, "emails_sent"),
                "calls_talked": _metric(call_rows, pk, "calls_talked"),
                "calls_inbound_talked": _metric(call_rows, pk, "calls_inbound_talked"),
                "calls_outbound_talked": _metric(call_rows, pk, "calls_outbound_talked"),
                "calls_missed": _metric(call_rows, pk, "calls_missed"),
                "calls_unlinked": _metric(call_rows, pk, "calls_unlinked"),
                "avg_talk_seconds": avg_talk_seconds,
                "avg_talk_label": _talk_label(avg_talk_seconds),
                "activities": _metric(activity_rows, pk, "activities"),
                "overdue_next_contact": overdue_rows.get(pk, 0),
                **_kpi(pk, everyone=False),
            },
        )

    grain = "week" if since is None else "day"
    focus = None
    if focus_user is not None:
        focus = {
            "user_id": focus_user.pk,
            "display_name": manager_display_name(focus_user),
        }
    return {
        "totals": totals,
        "managers": managers,
        "series": _build_series(
            leads=leads,
            calls=calls,
            quotes=quotes,
            since=since,
            until=until,
            grain=grain,
            call_talk=call_talk,
            call_missed=call_missed,
        ),
        "focus": focus,
        "since": since.isoformat() if since is not None else None,
        "until": until.isoformat(),
        "scoped": scoped,
    }


def sales_report_recipients() -> list[str]:
    """Profile emails of active staff in the Analyst group.

    The site field «почта отчёта РОП» and ``LEAD_NOTIFY_EMAIL`` are not
    used. An inactive account, a user outside the group, or a blank
    address is skipped. Duplicate addresses are sent once.
    """
    from accounts.roles import GROUP_ANALYST

    raw = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            groups__name=GROUP_ANALYST,
        )
        .exclude(email="")
        .order_by("pk")
        .values_list("email", flat=True)
    )
    seen: set[str] = set()
    result: list[str] = []
    for addr in raw:
        cleaned = addr.strip()
        key = cleaned.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    result.sort(key=str.lower)
    return result
