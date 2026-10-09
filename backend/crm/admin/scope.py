"""Manager scope helpers and list filters shared by CRM admin classes."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from cabinet.models import Order
from crm.models import Client, Quote
from crm.services import scope_clients_for_manager, scope_orders_for_manager, scope_quotes_for_manager
from leads.models import Lead
from leads.services import scope_leads_for_manager


def _scoped_lead_queryset(request: HttpRequest) -> QuerySet[Lead]:
    """Leads the current manager may attach to CRM rows."""
    return scope_leads_for_manager(Lead.objects.all(), request.user)


def _scoped_client_queryset(request: HttpRequest) -> QuerySet[Client]:
    return scope_clients_for_manager(Client.objects.all(), request.user)


def _scoped_quote_queryset(request: HttpRequest) -> QuerySet[Quote]:
    return scope_quotes_for_manager(Quote.objects.all(), request.user)


def _scoped_order_queryset(request: HttpRequest) -> QuerySet[Order]:
    return scope_orders_for_manager(Order.objects.all(), request.user)


_CLIENT_AND_LEAD = {"client": _scoped_client_queryset, "lead": _scoped_lead_queryset}


class OverdueNextContactFilter(admin.SimpleListFilter):
    """Clients whose next-contact reminder is in the past."""

    title = _("следующий контакт")
    parameter_name = "next_contact_overdue"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        """Single overdue option."""
        del request, model_admin
        return [("yes", "Просрочен")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Client]) -> QuerySet[Client]:
        """Keep cards with next_contact_at in the past."""
        del request
        if self.value() != "yes":
            return queryset
        return queryset.filter(
            next_contact_at__isnull=False,
            next_contact_at__lt=timezone.now(),
        )
