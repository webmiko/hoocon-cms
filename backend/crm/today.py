"""Today's planned calls for the admin home screen.

The list is short on purpose. A touch is in one group only: unassigned
first, then overdue ones that already have an owner, then the rest of
today. Tomorrow stays on the planned-call calendar.

The same owner rule as the planned-call list: a free call is shared,
another manager's call stays on their board. Head of sales still sees all.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.urls import reverse
from django.utils import timezone

from crm.phones import split_phone_numbers
from crm.telephony import normalize_phone_digits

_GROUP_LIMIT = 8
_OVERDUE_DAYS = 14


def build_today_board(user: Any) -> dict[str, Any] | None:
    """Groups for the «Сегодня» block, or None when the user cannot see calls.

    A manager sees free calls and their own. Another manager's call is not
    on this board. «Админ» and «Аналитик» still see every call.
    """
    if not getattr(user, "is_authenticated", False) or not user.has_perm("crm.view_plannedtouch"):
        return None
    from crm.models import PlannedTouch
    from crm.services import scope_planned_touches_for_manager

    now = timezone.now()
    start, end = _today_bounds(now)
    horizon = now - timedelta(days=_OVERDUE_DAYS)
    queryset = scope_planned_touches_for_manager(
        PlannedTouch.objects.filter(starts_at__gte=horizon, starts_at__lt=end)
        .select_related("company", "company__assignee", "client", "assignee")
        .prefetch_related("company__phones")
        .order_by("starts_at", "pk"),
        user,
    )
    unassigned: list[Any] = []
    overdue: list[Any] = []
    later: list[Any] = []
    for touch in queryset:
        if _owner(touch) is None:
            unassigned.append(touch)
        elif touch.starts_at < now:
            overdue.append(touch)
        elif touch.starts_at >= start:
            later.append(touch)
    can_assign = user.has_perm("crm.change_plannedtouch")
    groups = [
        _group("unassigned", "Без ответственного", unassigned, user, can_assign),
        _group("overdue", "Просрочено", overdue, user, can_assign),
        _group("later", "Ещё сегодня", later, user, can_assign),
    ]
    visible = [group for group in groups if group["items"] or group["more"]]
    return {
        "groups": visible,
        "empty": not visible,
        "all_url": reverse("admin:crm_plannedtouch_changelist"),
    }


def _today_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(timezone.localdate(now), datetime.min.time()))
    return start, start + timedelta(days=1)


def _group(
    key: str,
    title: str,
    touches: list[Any],
    user: Any,
    can_assign: bool,
) -> dict[str, Any]:
    shown = touches[:_GROUP_LIMIT]
    return {
        "key": key,
        "title": title,
        "items": [_card(touch, user, can_assign) for touch in shown],
        "more": max(0, len(touches) - _GROUP_LIMIT),
    }


def _card(touch: Any, user: Any, can_assign: bool) -> dict[str, Any]:
    local = timezone.localtime(touch.starts_at)
    when = local.strftime("%H:%M")
    if local.date() != timezone.localdate():
        when = local.strftime("%d.%m %H:%M")
    company = touch.company
    name = company.name if company is not None else touch.title
    url = reverse("admin:crm_plannedtouch_change", args=[touch.pk])
    if company is not None:
        url = reverse("admin:crm_company_change", args=[company.pk])
    assign_url = ""
    owner = _owner(touch)
    if owner is None and can_assign:
        assign_url = reverse("admin:crm_plannedtouch_assign_me", args=[touch.pk])
    return {
        "id": touch.pk,
        "when": when,
        "name": name,
        "url": url,
        "tel": _tel(company),
        "assign_url": assign_url,
        "owner": _person_name(owner),
        "mine": owner is not None and owner.pk == getattr(user, "pk", None),
    }


def _owner(touch: Any) -> Any:
    """The manager the company card belongs to, or whoever took this call."""
    company = touch.company
    if company is not None and company.assignee_id:
        return company.assignee
    return touch.assignee


def _person_name(user: Any) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip()
    return full or user.get_username()


def _tel(company: Any) -> str:
    if company is None:
        return ""
    number = ""
    phones = list(company.phones.all())
    if phones:
        number = phones[0].number
    if not number:
        parts = split_phone_numbers(company.phone or "")
        number = parts[0] if parts else ""
    digits = normalize_phone_digits(number)
    if not 10 <= len(digits) <= 15:
        return ""
    return f"+{digits}"
