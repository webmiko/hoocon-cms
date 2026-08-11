"""Admin for support conversations, messages, and schedule."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
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
from supportchat.services import (
    SupportChatError,
    add_staff_reply,
    count_staff_unread,
    message_sender_name,
    staff_public_name,
)


def _serialize_admin_messages(qs: QuerySet[Message]) -> list[dict[str, Any]]:
    """Serialize message rows for Admin messenger template / poll JSON."""
    rows: list[dict[str, Any]] = []
    for msg in qs:
        local = timezone.localtime(msg.created_at)
        rows.append(
            {
                "id": msg.pk,
                "direction": msg.direction,
                "body": msg.body,
                "sender_name": message_sender_name(msg),
                "outside_hours": msg.outside_hours,
                "created_at_iso": msg.created_at.isoformat(),
                "created_at_label": local.strftime("%d.%m.%Y %H:%M"),
            },
        )
    return rows


def _chat_messages_for_admin(
    conversation: Conversation,
    *,
    after_id: int | None = None,
) -> list[dict[str, Any]]:
    """Serialize messages for the messenger template (admin-only)."""
    qs = conversation.messages.select_related(
        "author",
        "conversation",
        "conversation__assignee",
    ).order_by("created_at", "id")
    if after_id is not None:
        qs = qs.filter(id__gt=after_id)
    return _serialize_admin_messages(qs)


@admin.register(Conversation)
class ConversationAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Unified support inbox with messenger change view."""

    list_display = (
        "unread_badge",
        "channel_badge",
        "display_name",
        "contact_email",
        "status",
        "assignee",
        "last_message_at",
        "last_preview",
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
    # Messages render in the messenger template (not a tabular inline).
    inlines = ()
    ordering = ("-last_message_at", "-id")
    change_form_template = "admin/supportchat/conversation/change_form.html"
    change_list_template = "admin/supportchat/conversation/change_list.html"
    actions = ("action_mark_read", "action_close")

    fieldsets = (
        (
            "Карточка диалога",
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

    def get_queryset(self, request: HttpRequest) -> QuerySet[Conversation]:
        return super().get_queryset(request).select_related("assignee").prefetch_related("messages")

    @admin.display(description="Inbox", ordering="staff_unread_count")
    def unread_badge(self, obj: Conversation) -> str:
        if obj.staff_unread_count <= 0:
            return "—"
        return format_html(
            '<span style="color:#b01010;font-weight:700;">● {}</span>',
            obj.staff_unread_count,
        )

    @admin.display(description="Канал", ordering="channel")
    def channel_badge(self, obj: Conversation) -> str:
        label = obj.get_channel_display()
        return format_html(
            '<span class="hoocon-channel-badge hoocon-channel-badge--{}">{}</span>',
            obj.channel,
            label,
        )

    @admin.display(description="Последнее")
    def last_preview(self, obj: Conversation) -> str:
        msgs = list(obj.messages.all())
        if not msgs:
            return "—"
        last = msgs[-1]
        prefix = "← " if last.direction == "inbound" else "→ "
        text = (last.body or "").replace("\n", " ").strip()
        if len(text) > 56:
            text = text[:55].rstrip() + "…"
        return f"{prefix}{text}"

    def get_urls(self) -> list[Any]:
        urls = super().get_urls()
        custom = [
            path(
                "unread-count/",
                self.admin_site.admin_view(self.unread_count_view),
                name="supportchat_conversation_unread_count",
            ),
            path(
                "<path:object_id>/messages/",
                self.admin_site.admin_view(self.messages_poll_view),
                name="supportchat_conversation_messages_poll",
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

    def messages_poll_view(self, request: HttpRequest, object_id: str) -> JsonResponse:
        """GET JSON messages newer than ?after= for live Admin messenger."""
        if not request.user.has_perm("supportchat.view_conversation"):
            return JsonResponse({"messages": []}, status=403)
        conversation = get_object_or_404(
            Conversation.objects.select_related("assignee"),
            pk=object_id,
        )
        after_raw = (request.GET.get("after") or "").strip()
        after_id = int(after_raw) if after_raw.isdigit() else 0
        payload = _chat_messages_for_admin(conversation, after_id=after_id)
        if conversation.staff_unread_count and request.user.has_perm(
            "supportchat.change_conversation",
        ):
            conversation.staff_unread_count = 0
            conversation.save(update_fields=["staff_unread_count", "updated_at"])
        response = JsonResponse({"messages": payload})
        response["Cache-Control"] = "no-store"
        return response

    def reply_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        change_url = reverse("admin:supportchat_conversation_change", args=[object_id])
        change_url = f"{change_url}#hoocon-messenger"
        if request.method != "POST":
            return HttpResponseRedirect(change_url)
        if not request.user.has_perm("supportchat.change_conversation"):
            messages.error(request, "Недостаточно прав для ответа.")
            return HttpResponseRedirect(change_url)
        conversation = get_object_or_404(Conversation, pk=object_id)
        body = (request.POST.get("reply_body") or "").strip()
        user = request.user
        if not user.is_authenticated:
            messages.error(request, "Недостаточно прав для ответа.")
            return HttpResponseRedirect(change_url)
        try:
            msg = add_staff_reply(conversation, body, author=user)
        except SupportChatError as exc:
            messages.error(request, str(exc))
            return HttpResponseRedirect(change_url)
        from supportchat.tasks import deliver_outbound_message

        deliver_outbound_message.delay(msg.pk)
        messages.success(request, "Ответ отправлен.")
        return HttpResponseRedirect(change_url)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra = dict(extra_context or {})
        conversation = get_object_or_404(
            Conversation.objects.select_related("assignee"),
            pk=object_id,
        )
        if conversation.staff_unread_count and request.user.has_perm(
            "supportchat.change_conversation",
        ):
            conversation.staff_unread_count = 0
            conversation.save(update_fields=["staff_unread_count", "updated_at"])
        extra["reply_url"] = reverse(
            "admin:supportchat_conversation_reply",
            args=[object_id],
        )
        extra["messages_poll_url"] = reverse(
            "admin:supportchat_conversation_messages_poll",
            args=[object_id],
        )
        chat_messages = _chat_messages_for_admin(conversation)
        extra["chat_messages"] = chat_messages
        extra["chat_last_message_id"] = chat_messages[-1]["id"] if chat_messages else 0
        label = (conversation.display_name or "").strip()
        extra["chat_client_initial"] = (label[:1] or "?").upper()
        extra["chat_assignee_name"] = staff_public_name(conversation.assignee)
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
