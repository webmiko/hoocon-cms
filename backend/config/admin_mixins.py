"""Shared Django Admin helpers (open button, Russian UX)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, QuerySet
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


ScopeFn = Callable[[HttpRequest], QuerySet[Any]]


class ScopedForeignKeyMixin:
    """Limit FK choices *and POST validation* to rows the user may see.

    Autocomplete widgets only filter the dropdown; without a scoped
    ``queryset`` any pk is accepted on submit. The value already stored on
    the edited object stays valid, so a record linked by automation can
    still be saved by its manager.
    """

    scoped_fk: Mapping[str, ScopeFn] = {}

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        scope = self.scoped_fk.get(db_field.name)
        if scope is not None:
            kwargs["queryset"] = self._scope_with_current(db_field, request, scope(request))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)  # type: ignore[misc]

    def _scope_with_current(self, db_field: Any, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        match = getattr(request, "resolver_match", None)
        object_id = (getattr(match, "kwargs", None) or {}).get("object_id")
        if not object_id:
            return queryset
        model = self.model  # type: ignore[attr-defined]
        try:
            current = model._default_manager.filter(pk=object_id).values_list(db_field.attname, flat=True).first()
        except (ValueError, ValidationError):
            return queryset
        if current is None:
            return queryset
        target = db_field.remote_field.model._default_manager
        return target.filter(Q(pk__in=queryset.values("pk")) | Q(pk=current))


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
