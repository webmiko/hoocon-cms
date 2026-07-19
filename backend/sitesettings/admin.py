"""Django Admin for SiteSettings singleton.

Spec: docs/security-baseline.md §3.2 — show_prices_on_site default False.
Нельзя создать вторую запись и нельзя удалить singleton.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from sitesettings.models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton Admin: edit only; no add/delete when row exists."""

    list_display = ("__str__", "show_prices_on_site", "updated_at")
    fields = ("show_prices_on_site", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Allow add only if singleton row is missing."""
        if SiteSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(
        self,
        request: HttpRequest | None,
        obj: Any = None,
    ) -> bool:
        """Never allow delete — singleton must remain."""
        return False
