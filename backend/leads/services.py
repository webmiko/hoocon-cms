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
    QuerySet,
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


def manager_rotation_queryset() -> QuerySet[Any]:
    """Active staff in group «Менеджер» with a non-empty login email.

    Returns:
        User queryset ordered by primary key (stable round-robin order).
    """
    from accounts.roles import GROUP_MANAGER

    return (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            groups__name=GROUP_MANAGER,
        )
        .exclude(email="")
        .order_by("pk")
        .distinct()
    )


def assign_lead_round_robin(lead: Lead) -> Any | None:
    """Assign the next manager from the rotation pool to ``lead``.

    Only runs when SiteSettings ``lead_routing_mode`` is an assign mode.
    Empty pool → no-op (returns None). Uses ``select_for_update`` on the
    SiteSettings singleton so concurrent creates advance the cursor safely.

    Args:
        lead: saved Lead (preferably already linked to a CRM Client).

    Returns:
        Assigned User, or None when mode is off / pool empty.
    """
    from sitesettings.models import SiteSettings

    with transaction.atomic():
        SiteSettings.load()
        site = SiteSettings.objects.select_for_update().get(
            pk=SiteSettings.SINGLETON_PK,
        )
        mode = site.lead_routing_mode
        if mode not in (
            SiteSettings.LeadRoutingMode.ASSIGN_SALES,
            SiteSettings.LeadRoutingMode.ASSIGN_MANAGER,
        ):
            return None

        managers = list(manager_rotation_queryset())
        if not managers:
            return None

        last_id = site.lead_rr_last_user_id
        ids = [user.pk for user in managers]
        if last_id is not None and last_id in ids:
            pick = managers[(ids.index(last_id) + 1) % len(managers)]
        else:
            pick = managers[0]

        site.lead_rr_last_user = pick
        site.save(update_fields=["lead_rr_last_user", "updated_at"])

        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        locked.assignee = pick
        locked.save(update_fields=["assignee", "updated_at"])

        if locked.client_id:
            from crm.models import Client as CrmClient

            client = CrmClient.objects.select_for_update().get(pk=locked.client_id)
            if client.assignee_id is None:
                client.assignee = pick
                client.save(update_fields=["assignee", "updated_at"])

        lead.refresh_from_db()
        return pick


def resolve_lead_notify_recipients(lead: Lead) -> list[str]:
    """Pick notification To: addresses for a new lead.

    ``assign_manager`` + assignee with email → that User.email.
    Otherwise → ``LEAD_NOTIFY_EMAIL`` (sales@ list).

    Args:
        lead: Lead (use ``select_related("assignee")`` when possible).

    Returns:
        Deduplicated recipient list (may be empty if env unset).
    """
    from sitesettings.models import SiteSettings

    sales = parse_notify_emails(getattr(settings, "LEAD_NOTIFY_EMAIL", "") or "")
    site = SiteSettings.load()
    if site.lead_routing_mode == SiteSettings.LeadRoutingMode.ASSIGN_MANAGER:
        assignee = getattr(lead, "assignee", None)
        if assignee is not None:
            addr = (getattr(assignee, "email", "") or "").strip()
            if addr:
                return parse_notify_emails(addr)
    return sales


def count_new_leads(*, user: Any | None = None) -> int:
    """Return unread new leads for the admin sticker / dashboard.

    Counts leads with status=new and seen_at IS NULL.
    When ``user`` is set and is not a superuser, count is limited to leads
    visible via :func:`scope_leads_for_manager` (unassigned NEW pool + own).

    Args:
        user: optional staff user for scoped counting.

    Returns:
        Non-negative count of unread new leads.
    """
    qs = Lead.objects.filter(
        status=Lead.LeadStatus.NEW,
        seen_at__isnull=True,
    )
    if user is not None:
        qs = scope_leads_for_manager(qs, user)
    return qs.count()


def scope_leads_for_manager(queryset: QuerySet[Lead], user: Any) -> QuerySet[Lead]:
    """Limit leads for a working manager in Admin.

    Superuser sees all. A regular staff manager sees:
    - unassigned new leads (shared pool: NEW and assignee IS NULL);
    - leads assigned to them (``assignee``), including NEW with assignee;
    - leads they finished (``processed_by``);
    - leads on CRM clients they own (``client.assignee``).

    Activity authorship does **not** unlock a foreign lead (closes IDOR via
    ``Activity.lead`` + author self-assignment).

    Args:
        queryset: base Lead queryset (may already be annotated).
        user: authenticated staff user.

    Returns:
        Filtered queryset (``.distinct()`` when joins are needed).
    """
    if getattr(user, "is_superuser", False):
        return queryset
    if not getattr(user, "is_authenticated", False) or not getattr(user, "pk", None):
        return queryset.none()

    return queryset.filter(
        Q(status=Lead.LeadStatus.NEW, assignee__isnull=True)
        | Q(assignee_id=user.pk)
        | Q(processed_by_id=user.pk)
        | Q(client__assignee_id=user.pk),
    ).distinct()


def lead_visible_to_manager(lead: Lead | None, user: Any) -> bool:
    """Whether ``user`` may link/see this lead under manager scope.

    Args:
        lead: Lead instance or None (None is always allowed for empty FK).
        user: staff user.

    Returns:
        True when lead is None or present in the scoped queryset.
    """
    if lead is None:
        return True
    return scope_leads_for_manager(Lead.objects.filter(pk=lead.pk), user).exists()


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


def take_lead_in_work(lead: Lead, manager: Any) -> tuple[Lead, bool]:
    """Assign lead to manager and set status to in_progress.

    Uses select_for_update; skips overwrite if another assignee already set.

    Args:
        lead: Lead to claim.
        manager: staff user taking the lead.

    Returns:
        ``(lead, taken)`` — ``taken`` is False when another assignee held it.
    """
    with transaction.atomic():
        locked = Lead.objects.select_for_update().get(pk=lead.pk)
        if locked.assignee_id and locked.assignee_id != manager.pk:
            lead.refresh_from_db()
            return lead, False
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
    return lead, True


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


def build_lead_processing_stats(
    *,
    since: datetime | None = None,
    queryset: QuerySet[Lead] | None = None,
) -> dict[str, Any]:
    """Aggregate lead processing totals and per-manager breakdown.

    Uses grouped annotations to avoid N+1 per manager.

    Args:
        since: optional lower bound for ``done_in_period`` / avg time
            (uses ``processed_at``).
        queryset: optional Lead queryset (manager scope). Defaults to all.

    Returns:
        Dict with ``totals``, ``managers``, ``since`` ISO string or None.
    """
    base = queryset if queryset is not None else Lead.objects.all()
    status_counts = {row["status"]: row["n"] for row in base.values("status").annotate(n=Count("id"))}
    totals: dict[str, Any] = {
        "new": status_counts.get(Lead.LeadStatus.NEW, 0),
        "in_progress": status_counts.get(Lead.LeadStatus.IN_PROGRESS, 0),
        "done": status_counts.get(Lead.LeadStatus.DONE, 0),
        "unassigned_open": base.filter(
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
    done_qs = base.filter(done_filter, processed_at__isnull=False)
    if since is not None:
        done_qs = done_qs.filter(processed_at__gte=since)
    totals["done_in_period"] = done_qs.count()
    avg_duration = done_qs.aggregate(avg_duration=Avg(duration))["avg_duration"]
    totals["avg_hours_to_done"] = round(avg_duration.total_seconds() / 3600, 1) if avg_duration else None

    assignee_rows = (
        base.exclude(assignee_id=None)
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
        base.exclude(processed_by_id=None)
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
