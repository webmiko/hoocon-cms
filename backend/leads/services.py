"""Lead notification helpers, manager assignment, and processing stats.

Admin stickers use count_new_leads(); Celery email uses render_lead_notification.
Manager ownership: assignee (в работе) / processed_by (завершил).
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parseaddr
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Q,
)
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from leads.models import Lead

User = get_user_model()


def parse_notify_emails(raw: str) -> list[str]:
    """Split LEAD_NOTIFY_EMAIL into unique addresses.

    Args:
        raw: comma- and/or semicolon-separated emails.

    Returns:
        Deduplicated list of non-empty addresses (order preserved).
    """
    seen: set[str] = set()
    result: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        addr = parseaddr(chunk.strip())[1].strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(addr)
    return result


def count_new_leads() -> int:
    """Return unread new leads for the admin sticker.

    Counts leads with status=new and seen_at IS NULL (not yet opened).

    Returns:
        Non-negative count of unread new leads.
    """
    return Lead.objects.filter(
        status=Lead.LeadStatus.NEW,
        seen_at__isnull=True,
    ).count()


def mark_lead_seen(lead_id: int) -> bool:
    """Mark a lead as seen when a manager opens it in Admin.

    Only updates rows that are still unseen. Does not change status
    (тег «Новая» остаётся до ручной смены статуса).

    Args:
        lead_id: Lead primary key.

    Returns:
        True if a row was updated.
    """
    updated = Lead.objects.filter(pk=lead_id, seen_at__isnull=True).update(
        seen_at=timezone.now(),
    )
    return updated > 0


def manager_display_name(user: Any) -> str:
    """Human-readable manager label for Admin / stats.

    Args:
        user: Django user instance.

    Returns:
        Full name, or username if name is empty.
    """
    full = (user.get_full_name() or "").strip()
    return full or user.get_username()


def take_lead_in_work(lead: Lead, manager: Any) -> Lead:
    """Assign lead to manager and set status to in_progress.

    Uses select_for_update; skips overwrite if another assignee already set.

    Args:
        lead: Lead to claim.
        manager: staff user taking the lead.

    Returns:
        Updated Lead instance (saved).
    """
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        if locked.assignee_id and locked.assignee_id != manager.pk:
            lead.refresh_from_db()
            return lead
        locked.assignee = manager
        locked.status = Lead.LeadStatus.IN_PROGRESS
        if locked.seen_at is None:
            locked.seen_at = timezone.now()
        locked.save(
            update_fields=["assignee", "status", "seen_at", "updated_at"],
        )
        lead.refresh_from_db()
    _log_manager_activity(
        lead,
        author=manager,
        subject=f"Взята в работу: {manager_display_name(manager)}",
        body="Статус → В работе",
    )
    return lead


def apply_lead_manager_on_save(lead: Lead, *, actor: Any) -> None:
    """Fill assignee / processed_* from status transitions (in-memory).

    Call before ``lead.save()`` from Admin ``save_model``.
    Leaving DONE clears processed_* so stats stay accurate.

    Args:
        lead: Lead being saved (may be unsaved status change).
        actor: current staff user performing the save.
    """
    if lead.status != Lead.LeadStatus.DONE:
        if lead.processed_by_id is not None or lead.processed_at is not None:
            lead.processed_by = None
            lead.processed_at = None
    if lead.status == Lead.LeadStatus.IN_PROGRESS and lead.assignee_id is None:
        lead.assignee = actor
    if lead.status == Lead.LeadStatus.DONE:
        if lead.processed_by_id is None:
            lead.processed_by = actor
        if lead.processed_at is None:
            lead.processed_at = timezone.now()
        if lead.assignee_id is None:
            lead.assignee = actor


def log_manager_activity(
    lead: Lead,
    *,
    author: Any,
    subject: str,
    body: str = "",
) -> None:
    """Public wrapper for CRM Activity on manager actions."""
    _log_manager_activity(lead, author=author, subject=subject, body=body)


def _log_manager_activity(
    lead: Lead,
    *,
    author: Any,
    subject: str,
    body: str = "",
) -> None:
    """Best-effort CRM Activity when manager ownership changes.

    Args:
        lead: related Lead (needs client for Activity).
        author: staff user.
        subject: short activity title.
        body: optional details.
    """
    if not lead.client_id:
        return
    from crm.models import Activity, ActivityType

    Activity.objects.create(
        client_id=lead.client_id,
        lead=lead,
        activity_type=ActivityType.STATUS,
        subject=subject[:300],
        body=body,
        author=author,
    )


def build_lead_processing_stats(*, since: datetime | None = None) -> dict[str, Any]:
    """Aggregate lead processing totals and per-manager breakdown.

    Uses grouped annotations to avoid N+1 per manager.

    Args:
        since: optional lower bound for ``done_in_period`` / avg time
            (uses ``processed_at``). Totals by status are always global.

    Returns:
        Dict with ``totals``, ``managers``, ``since`` ISO string or None.
    """
    status_counts = {row["status"]: row["n"] for row in Lead.objects.values("status").annotate(n=Count("id"))}
    totals: dict[str, Any] = {
        "new": status_counts.get(Lead.LeadStatus.NEW, 0),
        "in_progress": status_counts.get(Lead.LeadStatus.IN_PROGRESS, 0),
        "done": status_counts.get(Lead.LeadStatus.DONE, 0),
        "unassigned_open": Lead.objects.filter(
            status__in=(Lead.LeadStatus.NEW, Lead.LeadStatus.IN_PROGRESS),
            assignee__isnull=True,
        ).count(),
    }
    done_filter = Q(status=Lead.LeadStatus.DONE)
    period_done = done_filter
    if since is not None:
        period_done &= Q(processed_at__gte=since)

    duration = ExpressionWrapper(
        F("processed_at") - F("created_at"),
        output_field=DurationField(),
    )
    done_qs = Lead.objects.filter(done_filter, processed_at__isnull=False)
    if since is not None:
        done_qs = done_qs.filter(processed_at__gte=since)
    totals["done_in_period"] = done_qs.count()
    avg_duration = done_qs.aggregate(avg_duration=Avg(duration))["avg_duration"]
    totals["avg_hours_to_done"] = round(avg_duration.total_seconds() / 3600, 1) if avg_duration else None

    assignee_rows = (
        Lead.objects.exclude(assignee_id=None)
        .values("assignee_id")
        .annotate(
            assigned_open=Count(
                "id",
                filter=Q(status__in=(Lead.LeadStatus.NEW, Lead.LeadStatus.IN_PROGRESS)),
            ),
            in_progress=Count(
                "id",
                filter=Q(status=Lead.LeadStatus.IN_PROGRESS),
            ),
        )
    )
    processed_rows = (
        Lead.objects.exclude(processed_by_id=None)
        .filter(status=Lead.LeadStatus.DONE)
        .values("processed_by_id")
        .annotate(
            done_total=Count("id"),
            done_in_period=Count("id", filter=period_done),
            avg_duration=Avg(
                duration,
                filter=Q(processed_at__isnull=False) & period_done,
            ),
        )
    )
    by_assignee = {row["assignee_id"]: row for row in assignee_rows}
    by_processed = {row["processed_by_id"]: row for row in processed_rows}
    staff_ids = set(by_assignee) | set(by_processed)

    managers: list[dict[str, Any]] = []
    if staff_ids:
        users = User.objects.filter(pk__in=staff_ids).order_by("first_name", "username")
        for user in users:
            a = by_assignee.get(user.pk, {})
            p = by_processed.get(user.pk, {})
            mgr_avg = p.get("avg_duration")
            managers.append(
                {
                    "user_id": user.pk,
                    "username": user.get_username(),
                    "display_name": manager_display_name(user),
                    "assigned_open": a.get("assigned_open", 0),
                    "in_progress": a.get("in_progress", 0),
                    "done_total": p.get("done_total", 0),
                    "done_in_period": p.get("done_in_period", 0),
                    "avg_hours_to_done": (round(mgr_avg.total_seconds() / 3600, 1) if mgr_avg else None),
                },
            )

    managers.sort(key=lambda row: (-row["done_in_period"], -row["assigned_open"]))
    return {
        "totals": totals,
        "managers": managers,
        "since": since.isoformat() if since else None,
    }


def new_leads_changelist_url() -> str:
    """Relative Admin URL for unread new leads (matches sticker count).

    Returns:
        Path with status=new and seen_at empty.
    """
    base = reverse("admin:leads_lead_changelist")
    return f"{base}?status__exact=new&seen_at__isempty=1"


def build_lead_admin_url(lead_id: int) -> str:
    """Absolute Admin change URL for a lead (for email body).

    Args:
        lead_id: Lead primary key.

    Returns:
        Absolute URL using SITE_URL.
    """
    site = getattr(settings, "SITE_URL", "").rstrip("/") or "https://hoocon.ru"
    path = reverse("admin:leads_lead_change", args=[lead_id])
    return f"{site}{path}"


def render_lead_notification(lead: Lead) -> tuple[str, str, str]:
    """Build subject, plain text, and HTML bodies for a new-lead email.

    Args:
        lead: saved Lead instance (with optional sku).

    Returns:
        Tuple of (subject, text_body, html_body).
    """
    admin_url = build_lead_admin_url(lead.pk)
    inbox_url = (getattr(settings, "SITE_URL", "").rstrip("/") or "https://hoocon.ru") + new_leads_changelist_url()
    context = {
        "lead": lead,
        "admin_url": admin_url,
        "inbox_url": inbox_url,
        "lead_type_display": lead.get_lead_type_display(),
    }
    subject = f"Новая заявка #{lead.pk}: {lead.get_lead_type_display()} от {lead.name}"
    text_body = render_to_string("leads/email/new_lead.txt", context).strip()
    html_body = render_to_string("leads/email/new_lead.html", context).strip()
    return subject, text_body, html_body
