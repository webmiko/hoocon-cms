"""Admin home dashboard: stats, feeds, notifications for Unfold index."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

_FEED_LIMIT = 8
_LOG_LIMIT = 10
_STATS_DAYS = 30
_LOG_APP_LABELS = ("crm", "leads", "catalog")


def build_admin_dashboard(request: HttpRequest) -> dict[str, Any]:
    """Assemble dashboard payload for the Admin index.

    Args:
        request: authenticated staff request.

    Returns:
        Context keys under ``hoocon_dashboard`` (empty dict if anon).
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    can_leads = user.has_perm("leads.view_lead")
    can_crm = user.has_perm("crm.view_client")
    can_analytics = user.has_perm("analytics.view_pagedailystat")
    since = timezone.now() - timedelta(days=_STATS_DAYS)

    notifications = _build_notifications(
        user=user,
        can_leads=can_leads,
        can_crm=can_crm,
    )
    cards = _build_stat_cards(
        user=user,
        can_leads=can_leads,
        can_crm=can_crm,
        can_analytics=can_analytics,
        since=since,
    )
    chart = _build_status_chart(user=user) if can_leads else []

    recent_leads: list[dict[str, Any]] | None = None
    if can_leads:
        recent_leads = _recent_leads(user)

    recent_clients: list[dict[str, Any]] | None = None
    recent_activities: list[dict[str, Any]] | None = None
    if can_crm:
        recent_clients = _recent_clients(user)
        recent_activities = _recent_activities(user)

    admin_log = _recent_admin_log(user)

    links: dict[str, str] = {}
    if can_leads:
        links["leads"] = reverse("admin:leads_lead_changelist")
        links["leads_stats"] = reverse("admin:leads_lead_stats")
    if can_crm:
        links["clients"] = reverse("admin:crm_client_changelist")
        links["activities"] = reverse("admin:crm_activity_changelist")
    if can_analytics:
        links["analytics"] = reverse("admin:analytics_pagedailystat_stats")

    return {
        "hoocon_dashboard": {
            "period_days": _STATS_DAYS,
            "notifications": notifications,
            "cards": cards,
            "chart": chart,
            "recent_leads": recent_leads,
            "recent_clients": recent_clients,
            "recent_activities": recent_activities,
            "admin_log": admin_log,
            "links": links,
        },
    }


def _scoped_leads(user: Any) -> Any:
    """Lead queryset visible to this manager (or all for superuser)."""
    from leads.models import Lead
    from leads.services import scope_leads_for_manager

    return scope_leads_for_manager(Lead.objects.all(), user)


def _build_notifications(
    *,
    user: Any,
    can_leads: bool,
    can_crm: bool,
) -> list[dict[str, Any]]:
    """Unread / attention items for the alerts strip (scoped KPIs)."""
    items: list[dict[str, Any]] = []
    if can_leads:
        from leads.models import Lead
        from leads.services import count_new_leads, new_leads_changelist_url

        scoped = _scoped_leads(user)
        unread = count_new_leads(user=user)
        if unread:
            items.append(
                {
                    "level": "danger",
                    "title": f"Новые заявки без просмотра: {unread}",
                    "hint": "Откройте заявку — стикер счётчика обновится.",
                    "url": new_leads_changelist_url(),
                },
            )
        unassigned = scoped.filter(
            status__in=(Lead.LeadStatus.NEW, Lead.LeadStatus.IN_PROGRESS),
            assignee__isnull=True,
        ).count()
        if unassigned:
            items.append(
                {
                    "level": "warning",
                    "title": f"Без менеджера: {unassigned}",
                    "hint": "Возьмите в работу или назначьте ответственного.",
                    "url": reverse("admin:leads_lead_changelist"),
                },
            )
        if not user.is_superuser:
            mine_open = scoped.filter(
                assignee=user,
                status=Lead.LeadStatus.IN_PROGRESS,
            ).count()
            if mine_open:
                items.append(
                    {
                        "level": "info",
                        "title": f"У вас в работе: {mine_open}",
                        "hint": "Ваши открытые заявки.",
                        "url": reverse("admin:leads_lead_changelist"),
                    },
                )

    if can_crm:
        from crm.models import EmailMessage, EmailStatus
        from crm.services import scope_emails_for_manager

        failed = scope_emails_for_manager(
            EmailMessage.objects.filter(status=EmailStatus.FAILED),
            user,
        ).count()
        if failed:
            items.append(
                {
                    "level": "warning",
                    "title": f"Ошибки отправки писем: {failed}",
                    "hint": "Проверьте SMTP и повторите отправку из «Письма».",
                    "url": reverse("admin:crm_emailmessage_changelist"),
                },
            )

    if not items:
        items.append(
            {
                "level": "ok",
                "title": "Нет срочных оповещений",
                "hint": "Новые заявки и сбои появятся здесь.",
                "url": "",
            },
        )
    return items


def _build_stat_cards(
    *,
    user: Any,
    can_leads: bool,
    can_crm: bool,
    can_analytics: bool,
    since: Any,
) -> list[dict[str, Any]]:
    """KPI tiles for the dashboard grid (scoped for managers)."""
    cards: list[dict[str, Any]] = []
    if can_leads:
        from leads.services import build_lead_processing_stats, count_new_leads

        stats = build_lead_processing_stats(since=since, queryset=_scoped_leads(user))
        totals = stats["totals"]
        cards.extend(
            [
                {
                    "label": "Непросмотренные",
                    "value": count_new_leads(user=user),
                    "accent": True,
                    "url": reverse("admin:leads_lead_changelist"),
                },
                {
                    "label": "Новые",
                    "value": totals["new"],
                    "accent": False,
                    "url": reverse("admin:leads_lead_changelist"),
                },
                {
                    "label": "В работе",
                    "value": totals["in_progress"],
                    "accent": False,
                    "url": reverse("admin:leads_lead_changelist"),
                },
                {
                    "label": f"Закрыто за {_STATS_DAYS} дн.",
                    "value": totals["done_in_period"],
                    "accent": False,
                    "url": reverse("admin:leads_lead_stats"),
                },
            ],
        )
        if totals.get("avg_hours_to_done") is not None:
            cards.append(
                {
                    "label": "Среднее время, ч",
                    "value": totals["avg_hours_to_done"],
                    "accent": False,
                    "url": reverse("admin:leads_lead_stats"),
                },
            )

    if can_analytics:
        from analytics.models import SiteDailyStat

        today_row = SiteDailyStat.objects.filter(day=timezone.localdate()).first()
        cards.extend(
            [
                {
                    "label": "Просмотры сегодня",
                    "value": today_row.views if today_row else 0,
                    "accent": not can_leads,
                    "url": reverse("admin:analytics_pagedailystat_stats"),
                },
                {
                    "label": "Уникальные сегодня",
                    "value": today_row.unique_visitors if today_row else 0,
                    "accent": False,
                    "url": reverse("admin:analytics_pagedailystat_stats"),
                },
            ],
        )

    if can_crm:
        from crm.models import Client, EmailMessage, EmailStatus
        from crm.services import scope_clients_for_manager, scope_emails_for_manager

        clients_n = scope_clients_for_manager(
            Client.objects.filter(is_active=True),
            user,
        ).count()
        sent_period = scope_emails_for_manager(
            EmailMessage.objects.filter(
                status=EmailStatus.SENT,
                sent_at__gte=since,
            ),
            user,
        ).count()
        cards.extend(
            [
                {
                    "label": "Клиенты CRM",
                    "value": clients_n,
                    "accent": False,
                    "url": reverse("admin:crm_client_changelist"),
                },
                {
                    "label": f"Писем за {_STATS_DAYS} дн.",
                    "value": sent_period,
                    "accent": False,
                    "url": reverse("admin:crm_emailmessage_changelist"),
                },
            ],
        )
    return cards


def _build_status_chart(*, user: Any) -> list[dict[str, Any]]:
    """Simple bar data for lead status infographic."""
    from leads.models import Lead

    qs = _scoped_leads(user)
    rows = list(qs.values("status").annotate(n=Count("id")))
    by_status = {row["status"]: row["n"] for row in rows}
    order = (
        (Lead.LeadStatus.NEW, "Новые", "new"),
        (Lead.LeadStatus.IN_PROGRESS, "В работе", "progress"),
        (Lead.LeadStatus.DONE, "Завершены", "done"),
    )
    total = sum(by_status.get(key, 0) for key, _label, _css in order) or 1
    return [
        {
            "key": css,
            "label": label,
            "count": by_status.get(key, 0),
            "pct": round(100 * by_status.get(key, 0) / total),
        }
        for key, label, css in order
    ]


def _recent_leads(user: Any) -> list[dict[str, Any]]:
    """Latest leads visible to this manager."""
    qs = _scoped_leads(user).select_related("assignee", "client").order_by("-created_at", "-pk")[:_FEED_LIMIT]
    out: list[dict[str, Any]] = []
    for lead in qs:
        out.append(
            {
                "id": lead.pk,
                "title": str(lead),
                "name": lead.name,
                "company": lead.company or "—",
                "status": lead.get_status_display(),
                "status_key": lead.status,
                "created_at": lead.created_at,
                "url": reverse("admin:leads_lead_change", args=[lead.pk]),
            },
        )
    return out


def _recent_clients(user: Any) -> list[dict[str, Any]]:
    """Latest updated CRM client cards visible to this manager."""
    from crm.models import Client
    from crm.services import scope_clients_for_manager

    qs = (
        scope_clients_for_manager(Client.objects.all(), user)
        .select_related("assignee")
        .order_by("-updated_at")[:_FEED_LIMIT]
    )
    out: list[dict[str, Any]] = []
    for client in qs:
        out.append(
            {
                "id": client.pk,
                "email": client.email,
                "name": client.name,
                "company": client.company or "—",
                "updated_at": client.updated_at,
                "url": reverse("admin:crm_client_change", args=[client.pk]),
            },
        )
    return out


def _recent_activities(user: Any) -> list[dict[str, Any]]:
    """Latest CRM timeline events visible to this manager."""
    from crm.models import Activity
    from crm.services import scope_activities_for_manager

    qs = (
        scope_activities_for_manager(Activity.objects.all(), user)
        .select_related("client", "author", "lead")
        .order_by("-created_at")[:_FEED_LIMIT]
    )
    out: list[dict[str, Any]] = []
    for act in qs:
        out.append(
            {
                "id": act.pk,
                "type": act.get_activity_type_display(),
                "subject": act.subject or act.get_activity_type_display(),
                "client": str(act.client) if act.client_id else "—",
                "author": _username(act.author) if act.author_id else "—",
                "created_at": act.created_at,
                "url": reverse("admin:crm_activity_change", args=[act.pk]),
            },
        )
    return out


def _username(user: Any) -> str:
    """Safe username from a User FK (django-stubs types FKs loosely)."""
    if user is None:
        return "—"
    return cast(AbstractBaseUser, user).get_username()


def _recent_admin_log(user: Any) -> list[dict[str, Any]]:
    """Recent Admin LogEntry for catalog/CRM/leads (filter before slice)."""
    qs = LogEntry.objects.select_related("user", "content_type").order_by("-action_time")
    if not user.is_superuser:
        qs = qs.filter(user_id=user.pk)

    ct_ids = ContentType.objects.filter(app_label__in=_LOG_APP_LABELS).values("pk")
    qs = qs.filter(Q(content_type_id__in=ct_ids) | Q(content_type__isnull=True))
    entries = list(qs[:_LOG_LIMIT])

    out: list[dict[str, Any]] = []
    for entry in entries:
        model = ""
        if entry.content_type_id:
            ct = cast(ContentType, entry.content_type)
            model = f"{ct.app_label}.{ct.model}"
            if not model.startswith(tuple(f"{a}." for a in _LOG_APP_LABELS)):
                continue
        out.append(
            {
                "time": entry.action_time,
                "user": _username(entry.user) if entry.user_id else "—",
                "action": entry.get_action_flag_display(),
                "object": entry.object_repr,
                "model": model,
                "url": entry.get_admin_url() or "",
            },
        )
    return out[:_FEED_LIMIT]
