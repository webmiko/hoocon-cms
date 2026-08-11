"""Admin for support conversations, messages, and schedule."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin
from supportchat.models import (
    Conversation,
    ConversationStatus,
    Message,
    SupportSchedule,
    SupportScheduleDay,
    SupportScheduleInterval,
)
from supportchat.services import SupportChatError, add_staff_reply, count_staff_unread


class MessageInline(TabularInline):
    """Read-only message history on the conversation card."""

    model = Message
    extra = 0
    can_delete = False
    fields = ("created_at", "direction", "outside_hours", "body", "author")
    readonly_fields = fields
    ordering = ("created_at",)
    show_change_link = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Conversation)
class ConversationAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Unified support inbox."""

    list_display = (
        "unread_badge",
        "channel",
        "display_name",
        "contact_email",
        "status",
        "staff_unread_count",
        "assignee",
        "last_message_at",
    )
    list_display_links = ("display_name", "contact_email")
    list_filter = ("channel", "status", "assignee")
    search_fields = ("display_name", "contact_email", "external_user_id")
    readonly_fields = (
        "channel",
        "external_user_id",
        "last_message_at",
        "staff_unread_count",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("assignee", "client", "lead")
    inlines = (MessageInline,)
    ordering = ("-last_message_at", "-id")
    change_form_template = "admin/supportchat/conversation/change_form.html"
    actions = ("action_mark_read", "action_close")

    fieldsets = (
        (
            "Диалог",
            {
                "fields": (
                    "channel",
                    "external_user_id",
                    "status",
                    "display_name",
                    "contact_email",
                    "assignee",
                ),
            },
        ),
        (
            "CRM",
            {
                "fields": ("client", "lead"),
                "classes": ("collapse",),
            },
        ),
        (
            "Метаданные",
            {
                "fields": (
                    "staff_unread_count",
                    "last_message_at",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Inbox", ordering="staff_unread_count")
    def unread_badge(self, obj: Conversation) -> str:
        if obj.staff_unread_count <= 0:
            return "—"
        return format_html(
            '<span style="color:#b01010;font-weight:700;">● {}</span>',
            obj.staff_unread_count,
        )

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "unread-count/",
                self.admin_site.admin_view(self.unread_count_view),
                name="supportchat_conversation_unread_count",
            ),
            path(
                "<path:object_id>/reply/",
                self.admin_site.admin_view(self.reply_view),
                name="supportchat_conversation_reply",
            ),
        ]
        return custom + urls

    def unread_count_view(self, request: HttpRequest) -> JsonResponse:
        if not request.user.has_perm("supportchat.view_conversation"):
            return JsonResponse({"count": 0})
        return JsonResponse({"count": count_staff_unread()})

    def reply_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        if request.method != "POST":
            return HttpResponseRedirect(
                reverse("admin:supportchat_conversation_change", args=[object_id]),
            )
        if not request.user.has_perm("supportchat.change_conversation"):
            messages.error(request, "Недостаточно прав для ответа.")
            return HttpResponseRedirect(
                reverse("admin:supportchat_conversation_change", args=[object_id]),
            )
        conversation = get_object_or_404(Conversation, pk=object_id)
        body = (request.POST.get("reply_body") or "").strip()
        user = request.user
        if not user.is_authenticated:
            messages.error(request, "Недостаточно прав для ответа.")
            return HttpResponseRedirect(
                reverse("admin:supportchat_conversation_change", args=[object_id]),
            )
        try:
            msg = add_staff_reply(conversation, body, author=user)
        except SupportChatError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(
                reverse("admin:supportchat_conversation_change", args=[object_id]),
            )
        from supportchat.tasks import deliver_outbound_message

        deliver_outbound_message.delay(msg.pk)
        messages.success(request, "Ответ отправлен.")
        return HttpResponseRedirect(
            reverse("admin:supportchat_conversation_change", args=[object_id]),
        )

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra = dict(extra_context or {})
        conversation = get_object_or_404(Conversation, pk=object_id)
        if conversation.staff_unread_count and request.user.has_perm(
            "supportchat.change_conversation",
        ):
            conversation.staff_unread_count = 0
            conversation.save(update_fields=["staff_unread_count", "updated_at"])
        extra["reply_url"] = reverse(
            "admin:supportchat_conversation_reply",
            args=[object_id],
        )
        return super().change_view(request, object_id, form_url, extra)

    @admin.action(description="Отметить прочитанными")
    def action_mark_read(
        self,
        request: HttpRequest,
        queryset: QuerySet[Conversation],
    ) -> None:
        updated = queryset.update(staff_unread_count=0)
        self.message_user(request, f"Прочитано: {updated}")

    @admin.action(description="Закрыть диалоги")
    def action_close(
        self,
        request: HttpRequest,
        queryset: QuerySet[Conversation],
    ) -> None:
        updated = queryset.update(status=ConversationStatus.CLOSED)
        self.message_user(request, f"Закрыто: {updated}")


class SupportScheduleIntervalInline(TabularInline):
    model = SupportScheduleInterval
    extra = 1
    fields = ("start_time", "end_time")


class SupportScheduleDayInline(TabularInline):
    model = SupportScheduleDay
    extra = 0
    fields = ("weekday", "is_closed")
    show_change_link = True
    # Intervals edited on day change — keep day list simple.
    max_num = 7


@admin.register(SupportScheduleDay)
class SupportScheduleDayAdmin(ModelAdmin):
    list_display = ("__str__", "weekday", "is_closed", "schedule")
    list_filter = ("is_closed", "weekday")
    inlines = (SupportScheduleIntervalInline,)
    ordering = ("weekday",)


@admin.register(SupportSchedule)
class SupportScheduleAdmin(ModelAdmin):
    list_display = ("__str__", "timezone", "updated_at")
    inlines = (SupportScheduleDayInline,)
    fields = ("timezone", "auto_reply_outside_hours", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not SupportSchedule.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        schedule = SupportSchedule.load()
        return redirect(
            reverse("admin:supportchat_supportschedule_change", args=[schedule.pk]),
        )


@admin.register(Message)
class MessageAdmin(ModelAdmin):
    """Optional message list for debugging (staff)."""

    list_display = (
        "id",
        "conversation",
        "direction",
        "outside_hours",
        "created_at",
        "short_body",
    )
    list_filter = ("direction", "outside_hours", "conversation__channel")
    search_fields = ("body", "external_message_id")
    readonly_fields = (
        "conversation",
        "direction",
        "body",
        "external_message_id",
        "author",
        "outside_hours",
        "raw_payload",
        "created_at",
    )

    @admin.display(description="текст")
    def short_body(self, obj: Message) -> str:
        return obj.body[:80]

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
