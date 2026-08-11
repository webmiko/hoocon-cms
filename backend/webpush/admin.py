"""Admin for push subscriptions and marketing broadcast."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from unfold.admin import ModelAdmin

from webpush.models import PushSubscription
from webpush.tasks import broadcast_marketing_push


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ModelAdmin):
    """List subscriptions; custom broadcast view for marketing."""

    change_list_template = "admin/webpush/pushsubscription/change_list.html"
    list_display = (
        "id",
        "short_endpoint",
        "user",
        "topic_support",
        "topic_marketing",
        "last_seen_at",
    )
    list_filter = ("topic_support", "topic_marketing")
    search_fields = ("endpoint", "session_key", "user__email", "user__username")
    readonly_fields = (
        "endpoint",
        "p256dh",
        "auth",
        "user",
        "session_key",
        "created_at",
        "last_seen_at",
    )
    ordering = ("-last_seen_at",)

    @admin.display(description="endpoint")
    def short_endpoint(self, obj: PushSubscription) -> str:
        return obj.endpoint[:64] + ("…" if len(obj.endpoint) > 64 else "")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "broadcast/",
                self.admin_site.admin_view(self.broadcast_view),
                name="webpush_pushsubscription_broadcast",
            ),
        ]
        return custom + urls

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra = dict(extra_context or {})
        extra["broadcast_url"] = reverse("admin:webpush_pushsubscription_broadcast")
        return super().changelist_view(request, extra)

    def broadcast_view(self, request: HttpRequest) -> HttpResponse:
        if not request.user.has_perm("webpush.change_pushsubscription"):
            messages.error(request, "Недостаточно прав.")
            return HttpResponseRedirect(
                reverse("admin:webpush_pushsubscription_changelist"),
            )
        if request.method == "POST":
            title = (request.POST.get("title") or "").strip()
            body = (request.POST.get("body") or "").strip()
            url = (request.POST.get("url") or "/").strip() or "/"
            if not title or not body:
                messages.error(request, "Заголовок и текст обязательны.")
            else:
                broadcast_marketing_push.delay(title=title, body=body, url=url)
                messages.success(request, "Рассылка поставлена в очередь.")
                return HttpResponseRedirect(
                    reverse("admin:webpush_pushsubscription_changelist"),
                )
        context = {
            **self.admin_site.each_context(request),
            "title": "Push-рассылка (маркетинг)",
            "opts": self.model._meta,
        }
        return render(request, "admin/webpush/broadcast.html", context)
