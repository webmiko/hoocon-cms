"""Shared Django Admin helpers (open button, Russian UX)."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html


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
