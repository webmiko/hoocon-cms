"""Django Admin for SEO Redirect map (Tilda → CMS).

Spec: docs/seo-url-migration.md §3; ПЛАН §6 Iter 1.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from redirects.models import Redirect


@admin.register(Redirect)
class RedirectAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for Redirect — from_path → to_path (301/302)."""

    list_display = ("from_path", "to_path", "status_code", "is_active", "edited_in_admin", "updated_at")
    list_display_links = ("from_path",)
    list_filter = ("status_code", "is_active", "edited_in_admin")
    search_fields = ("from_path", "to_path")
    ordering = ("from_path",)

    def save_model(self, request: HttpRequest, obj: Redirect, form: Any, change: bool) -> None:
        """Any Admin edit locks the row from ETL; an explicit checkbox change wins."""
        if "edited_in_admin" not in (form.changed_data or []):
            obj.edited_in_admin = True
        super().save_model(request, obj, form, change)
