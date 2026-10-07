"""Shared Django Admin helpers (open button, Russian UX)."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db import models
from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html


def filter_autocomplete_by_client(
    request: HttpRequest,
    qs: QuerySet[Any],
) -> QuerySet[Any]:
    """On ``/admin/autocomplete/`` narrow the queryset to ``?client=<id>``.

    Paired with ``hoocon-admin-chained-autocomplete.js``: autocomplete
    widgets chained to a «клиент» field (lead/quote/order) send the
    selected client id; the *target* model's admin applies it here.
    Outside the autocomplete endpoint (changelist, widgets) the
    queryset is returned untouched.

    Args:
        request: current admin request.
        qs: target-model queryset already built by ``get_queryset``.

    Returns:
        Queryset filtered by ``client_id`` when the param is a digit.
    """
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") or ""
    if url_name != "autocomplete":
        return qs
    client_id = request.GET.get("client", "")
    if client_id.isdigit():
        return qs.filter(client_id=int(client_id))
    return qs


class OpenChangeLinkMixin:
    """Append «Открыть» to changelist so cards/tables need no ID click.

    Prefer a human ``list_display_links`` field; this button is the primary
    open control on stacked card layouts.
    """

    @admin.display(description="")
    def open_link(self, obj: models.Model) -> str:
        """Render a primary open button for the change form.

        Args:
            obj: Row model instance.

        Returns:
            Safe HTML anchor styled as a button.
        """
        opts = self.opts  # type: ignore[attr-defined]
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_change",
            args=[obj.pk],
        )
        return format_html(
            '<a class="hoocon-admin-open hoocon-admin-lead-open" href="{}">Открыть</a>',
            url,
        )

    def get_list_display(self, request: HttpRequest) -> tuple[Any, ...]:
        """Ensure ``open_link`` is the last changelist column."""
        display = list(super().get_list_display(request))  # type: ignore[misc]
        if "open_link" in display:
            display.remove("open_link")
        # Legacy LeadAdmin column name — drop before appending open_link.
        if "open_lead" in display:
            display.remove("open_lead")
        display.append("open_link")
        return tuple(display)
