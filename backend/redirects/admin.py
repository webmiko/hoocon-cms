"""Django Admin for SEO Redirect map (Tilda → CMS).

Spec: docs/seo-url-migration.md §3; ПЛАН §6 Iter 1.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from redirects.models import Redirect


@admin.register(Redirect)
class RedirectAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for Redirect — from_path → to_path (301/302)."""

    list_display = ("from_path", "to_path", "status_code", "is_active", "updated_at")
    list_display_links = ("from_path",)
    list_filter = ("status_code", "is_active")
    search_fields = ("from_path", "to_path")
    ordering = ("from_path",)
