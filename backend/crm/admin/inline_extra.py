"""Inline UX: one blank row when the parent has no lines yet."""

from __future__ import annotations

from typing import Any

from django.forms.models import _get_foreign_key
from django.http import HttpRequest


class OneBlankInlineRowMixin:
    """Show a single empty inline form until the first row is saved.

    Stops at ``extra = 0`` once rows exist so changelists do not keep a spare line.
    """

    extra = 0

    def _inline_fk_name(self) -> str | None:
        """FK field on the inline model pointing at the parent (same as formset factory)."""
        host: Any = self
        try:
            fk = _get_foreign_key(host.parent_model, host.model, fk_name=host.fk_name)
        except ValueError:
            return None
        return fk.name

    def get_extra(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> int:
        host: Any = self
        if not host.has_add_permission(request, obj):
            return 0
        if obj is None or obj.pk is None:
            return 1
        fk_name = host._inline_fk_name()
        if not fk_name:
            return 0
        has_rows = host.get_queryset(request).filter(**{fk_name: obj}).exists()
        return 0 if has_rows else 1
