"""List filters shared by company cards and leads."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.http import HttpRequest
from django.utils import timezone
from unfold.contrib.filters.admin import DropdownFilter

from accounts.roles import GROUP_MANAGER
from leads.services import manager_display_name


class ManagerFilter(DropdownFilter):
    """Rows of one manager, by the name other managers know.

    ``user_field`` is the FK column on the listed model (``assignee_id`` on a
    company, ``created_by_id`` on a letter).
    """

    title = "менеджер"
    parameter_name = "manager"
    user_field = "assignee_id"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        """Active managers, plus anyone who still owns a row in this list."""
        user_model = get_user_model()
        assigned = model_admin.get_queryset(request).exclude(**{self.user_field: None}).values(self.user_field)
        people = (
            user_model.objects.filter(
                Q(is_active=True, is_staff=True, groups__name=GROUP_MANAGER) | Q(pk__in=assigned),
            )
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
        return [(str(user.pk), manager_display_name(user)) for user in people]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        """Keep rows of the chosen user. Anything else is the full list."""
        del request
        raw = str(self.value() or "").strip()
        if not raw.isdigit():
            return queryset
        return queryset.filter(**{self.user_field: int(raw)})


class EmailAuthorFilter(ManagerFilter):
    """Letters composed by one manager. Inbound mail has no author and stays out."""

    user_field = "created_by_id"


class WorkQueueFilter(admin.SimpleListFilter):
    """Shortcuts from the outreach workbook: callable, prepaid, today, overdue."""

    title = "очередь"
    parameter_name = "work_queue"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        del request, model_admin
        return [
            ("callable", "Можно звонить"),
            ("do_not_call", "Не звонить"),
            ("today", "Звонок сегодня"),
            ("overdue", "Просрочен контакт"),
            ("prepaid", "Только предоплата"),
            ("low", "Хвост очереди"),
            ("need_data", "Нужны данные"),
            ("unassigned", "Без ответственного"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        del request
        value = self.value()
        if not value:
            return queryset
        if value == "callable":
            return queryset.exclude(work_labels__code="do_not_call").distinct()
        if value == "do_not_call":
            return queryset.filter(work_labels__code="do_not_call").distinct()
        if value == "prepaid":
            return queryset.filter(work_labels__code="prepaid_only").distinct()
        if value == "low":
            return queryset.filter(work_labels__code="low_priority").distinct()
        if value == "need_data":
            return queryset.filter(work_labels__code="need_data").distinct()
        if value == "unassigned":
            return queryset.filter(assignee__isnull=True)
        start, end = _today_bounds()
        if value == "today":
            if _has_field(queryset, "next_contact_at"):
                return queryset.filter(next_contact_at__gte=start, next_contact_at__lt=end)
            return queryset.filter(
                planned_touches__starts_at__gte=start,
                planned_touches__starts_at__lt=end,
            ).distinct()
        if value == "overdue":
            now = timezone.now()
            if _has_field(queryset, "next_contact_at"):
                return queryset.filter(next_contact_at__isnull=False, next_contact_at__lt=now)
            return queryset.filter(
                planned_touches__starts_at__lt=now,
                planned_touches__starts_at__gte=now - timedelta(days=14),
            ).distinct()
        return queryset


def _has_field(queryset: QuerySet[Any], name: str) -> bool:
    return any(field.name == name for field in queryset.model._meta.fields)


def _today_bounds() -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time()))
    return start, start + timedelta(days=1)
