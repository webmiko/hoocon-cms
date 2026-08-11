"""Admin for push subscriptions and marketing broadcast."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, Q, QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from unfold.admin import ModelAdmin

from webpush.models import PushSubscription
from webpush.tasks import broadcast_marketing_push


@admin.register(PushSubscription)
class PushSubscriptionAdmin(ModelAdmin):
    """List subscriptions; custom broadcast view for marketing."""

    change_list_template = "admin/webpush/pushsubscription/change_list.html"
    list_display = (
        "id",
        "topics_badge",
        "subscriber",
        "short_endpoint",
        "last_seen_at",
        "created_at",
    )
    list_display_links = ("id", "subscriber")
    list_filter = ("topic_support", "topic_marketing", "created_at")
    search_fields = ("endpoint", "session_key", "user__email", "user__username")
    readonly_fields = (
        "endpoint",
        "p256dh",
        "auth",
        "user",
        "session_key",
        "topic_support",
        "topic_marketing",
        "created_at",
        "last_seen_at",
    )
    ordering = ("-last_seen_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Темы")
    def topics_badge(self, obj: PushSubscription) -> str:
        chips: list[tuple[str, str]] = []
        if obj.topic_support:
            chips.append(("support", "Чат"))
        if obj.topic_marketing:
            chips.append(("marketing", "Новости"))
        if not chips:
            return format_html(
                '<span class="hoocon-push-topic hoocon-push-topic--none">нет</span>',
            )
        return format_html(
            '<span class="hoocon-push-topics">{}</span>',
            format_html_join(
                "",
                ('<span class="hoocon-push-topic hoocon-push-topic--{}">{}</span>'),
                chips,
            ),
        )

    @admin.display(description="Подписчик", ordering="user__email")
    def subscriber(self, obj: PushSubscription) -> str:
        if obj.user_id and obj.user is not None:
            raw = obj.user.get_username() or obj.user.email or f"#{obj.user_id}"
            label = raw.strip()
            return format_html(
                '<div class="hoocon-push-subscriber">'
                '<span class="hoocon-push-subscriber__name">{}</span>'
                '<span class="hoocon-push-subscriber__meta">staff / user</span>'
                "</div>",
                label,
            )
        key = (obj.session_key or "").strip()
        short = f"{key[:10]}…" if len(key) > 10 else (key or "—")
        return format_html(
            '<div class="hoocon-push-subscriber">'
            '<span class="hoocon-push-subscriber__name">Гость</span>'
            '<span class="hoocon-push-subscriber__meta">session {}</span>'
            "</div>",
            short,
        )

    @admin.display(description="Endpoint")
    def short_endpoint(self, obj: PushSubscription) -> str:
        text = obj.endpoint[:56] + ("…" if len(obj.endpoint) > 56 else "")
        return format_html('<span class="hoocon-push-endpoint">{}</span>', text)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[PushSubscription]:
        return super().get_queryset(request).select_related("user")

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
        stats = PushSubscription.objects.aggregate(
            total=Count("id"),
            support=Count("id", filter=Q(topic_support=True)),
            marketing=Count("id", filter=Q(topic_marketing=True)),
        )
        extra["push_stats"] = stats
        return super().changelist_view(request, extra)

    def broadcast_view(self, request: HttpRequest) -> HttpResponse:
        if not request.user.has_perm("webpush.change_pushsubscription"):
            messages.error(request, "Недостаточно прав.")
            return HttpResponseRedirect(
                reverse("admin:webpush_pushsubscription_changelist"),
            )
        marketing_count = PushSubscription.objects.filter(topic_marketing=True).count()
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
            "marketing_count": marketing_count,
            "changelist_url": reverse("admin:webpush_pushsubscription_changelist"),
        }
        return render(request, "admin/webpush/broadcast.html", context)
