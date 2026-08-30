"""Admin for first-party site analytics (stats page + read-only lists)."""

from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from analytics.models import PageDailyStat, SiteDailyStat
from analytics.services import build_site_analytics_stats


@admin.register(PageDailyStat)
class PageDailyStatAdmin(ModelAdmin):
    """Read-only daily path stats; custom overview at ``stats/``."""

    change_list_template = "admin/analytics/pagedailystat/change_list.html"
    list_display = (
        "day",
        "path",
        "object_type",
        "object_key",
        "title",
        "views",
        "unique_visitors",
    )
    list_filter = ("object_type", "day")
    search_fields = ("path", "object_key", "title")
    date_hierarchy = "day"
    ordering = ("-day", "-views")
    readonly_fields = (
        "day",
        "path",
        "object_type",
        "object_key",
        "title",
        "views",
        "unique_visitors",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: PageDailyStat | None = None,
    ) -> bool:
        del request, obj
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: PageDailyStat | None = None,
    ) -> bool:
        return bool(request.user and request.user.is_superuser)

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict | None = None,
    ) -> HttpResponse:
        extra = dict(extra_context or {})
        extra["hoocon_analytics_stats_url"] = reverse(
            "admin:analytics_pagedailystat_stats",
        )
        return super().changelist_view(request, extra_context=extra)

    def get_urls(self) -> list:
        custom = [
            path(
                "stats/",
                self.admin_site.admin_view(self.stats_view),
                name="analytics_pagedailystat_stats",
            ),
        ]
        return custom + super().get_urls()

    def stats_view(self, request: HttpRequest) -> HttpResponse:
        """Overview: totals, top pages, top SKUs."""
        if not request.user.has_perm("analytics.view_pagedailystat"):
            raise PermissionDenied
        raw_days = request.GET.get("days", "30")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 30
        if days < 0:
            days = 30
        stats = build_site_analytics_stats(days=days)
        context = {
            **self.admin_site.each_context(request),
            "title": "Аналитика сайта",
            "stats": stats,
            "days": days,
            "opts": self.model._meta,
            "changelist_url": reverse("admin:analytics_pagedailystat_changelist"),
        }
        return render(request, "admin/analytics/stats.html", context)


@admin.register(SiteDailyStat)
class SiteDailyStatAdmin(ModelAdmin):
    """Read-only site-wide daily totals."""

    list_display = ("day", "views", "unique_visitors")
    list_filter = ("day",)
    date_hierarchy = "day"
    ordering = ("-day",)
    readonly_fields = ("day", "views", "unique_visitors")

    def has_add_permission(self, request: HttpRequest) -> bool:
        del request
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: SiteDailyStat | None = None,
    ) -> bool:
        del request, obj
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: SiteDailyStat | None = None,
    ) -> bool:
        return bool(request.user and request.user.is_superuser)
