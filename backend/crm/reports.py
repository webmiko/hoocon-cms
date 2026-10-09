"""Sales-manager performance report for the head of sales (РОП)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from accounts.roles import GROUP_MANAGER, staff_sees_all_leads
from cabinet.models import Order
from crm.models import Activity, Call, Client, EmailMessage, EmailStatus, Quote, QuoteStatus
from leads.models import Lead
from leads.services import manager_display_name

User = get_user_model()


def _metric(rows: dict[Any, Any], key_id: int, field: str) -> int:
    """Read one annotated counter; missing manager or field is zero."""
    raw = rows.get(key_id)
    if raw is None:
        return 0
    bucket = cast("dict[str, int]", raw)
    return int(bucket.get(field, 0))


def build_sales_report(
    *,
    since: datetime | None,
    until: datetime | None = None,
    user: Any | None = None,
) -> dict[str, Any]:
    """Per-manager funnel counts for a period.

    Head of sales (``staff_sees_all_leads``) sees every manager; a scoped
    manager gets a single own row. Unassigned activity is a separate row.

    Args:
        since: inclusive lower bound (None = all time).
        until: exclusive upper bound (None = now).
        user: viewer; None = unscoped (Celery mail).

    Returns:
        ``totals``, ``managers``, ``since``/``until`` ISO strings.
    """
    until = until or timezone.now()
    scoped = user is not None and not staff_sees_all_leads(user)
    focus_id = user.pk if scoped and user is not None else None

    lead_created = Q()
    lead_done = Q(status=Lead.LeadStatus.DONE)
    quote_created = Q()
    # Issued once = sent_at stamped; accepted/rejected КП were sent too.
    quote_sent = Q(sent_at__isnull=False)
    quote_accepted = Q(status=QuoteStatus.ACCEPTED)
    order_created = Q()
    email_sent = Q(status=EmailStatus.SENT)
    call_talk = Q(talk_duration__gt=0)
    activity_created = Q()
    if since is not None:
        lead_created &= Q(created_at__gte=since)
        lead_done &= Q(processed_at__gte=since)
        quote_created &= Q(created_at__gte=since)
        quote_sent &= Q(sent_at__gte=since)
        quote_accepted &= Q(updated_at__gte=since)
        order_created &= Q(created_at__gte=since)
        email_sent &= Q(sent_at__gte=since)
        call_talk &= Q(started_at__gte=since)
        activity_created &= Q(created_at__gte=since)
    lead_created &= Q(created_at__lt=until)
    lead_done &= Q(processed_at__lt=until)
    quote_created &= Q(created_at__lt=until)
    quote_sent &= Q(sent_at__lt=until)
    quote_accepted &= Q(updated_at__lt=until)
    order_created &= Q(created_at__lt=until)
    email_sent &= Q(sent_at__lt=until)
    call_talk &= Q(started_at__lt=until)
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

    totals = {
        "leads_new": leads.filter(lead_created).count(),
        "leads_done": leads.filter(lead_done).count(),
        "quotes_created": quotes.filter(quote_created).count(),
        "quotes_sent": quotes.filter(quote_sent).count(),
        "quotes_accepted": quotes.filter(quote_accepted).count(),
        "orders_created": orders.filter(order_created).count(),
        "emails_sent": emails.filter(email_sent).count(),
        "calls_talked": calls.filter(call_talk).count(),
        "activities": activities.filter(activity_created).count(),
        "overdue_next_contact": overdue_next,
        "open_quotes": quotes.filter(
            status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT),
        ).count(),
    }

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
        .annotate(calls_talked=Count("id", filter=call_talk))
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

    managers: list[dict[str, Any]] = []
    users = User.objects.filter(pk__in=staff_ids).order_by("first_name", "username")
    for staff in users:
        pk = staff.pk
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
                "activities": _metric(activity_rows, pk, "activities"),
                "overdue_next_contact": overdue_rows.get(pk, 0),
            },
        )

    return {
        "totals": totals,
        "managers": managers,
        "since": since.isoformat() if since is not None else None,
        "until": until.isoformat(),
        "scoped": scoped,
    }


def sales_report_recipients() -> list[str]:
    """Emails for the weekly РОП digest (settings, else sales inbox)."""
    from django.conf import settings as django_settings

    from leads.services import parse_notify_emails
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    raw = (site.rop_report_email or "").strip()
    if raw:
        return parse_notify_emails(raw)
    return parse_notify_emails(getattr(django_settings, "LEAD_NOTIFY_EMAIL", "") or "")
