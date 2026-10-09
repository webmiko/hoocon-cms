"""Email messages, templates, attachments and mailbox state admin."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin, ScopedForeignKeyMixin
from config.unfold_callbacks import _versioned_static
from crm.admin.scope import _CLIENT_AND_LEAD
from crm.models import Client, EmailAttachment, EmailMessage, EmailStatus, EmailTemplate, InboundMailboxState
from crm.services import scope_emails_for_manager
from leads.models import Lead
from leads.services import lead_visible_to_manager


class EmailAttachmentInline(TabularInline):
    """Read-only attachments of an inbound message (private download)."""

    model = EmailAttachment
    extra = 0
    max_num = 0
    can_delete = False
    show_change_link = False
    fields = ("download_link", "content_type", "size")
    readonly_fields = fields
    verbose_name = "вложение"
    verbose_name_plural = "вложения"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Attachments arrive via IMAP only — no manual add."""
        return False

    @admin.display(description="файл")
    def download_link(self, obj: EmailAttachment) -> str:
        """Staff download link through the scoped admin view."""
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:crm_emailattachment_download", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.filename)


@admin.register(EmailMessage)
class EmailMessageAdmin(ScopedForeignKeyMixin, OpenChangeLinkMixin, ModelAdmin):
    """Outbound/inbound email log; staff can resend failed/draft.

    ID = email клиента (или to_email); одинаковые ID группируются.
    """

    inlines = (EmailAttachmentInline,)

    list_display = (
        "client_email_id",
        "direction",
        "status",
        "to_email",
        "subject",
        "client",
        "created_at",
        "sent_at",
    )
    list_display_links = ("subject",)
    list_filter = ("direction", "status", "created_at")
    search_fields = ("subject", "to_email", "from_email", "client__name", "client__email", "body")
    autocomplete_fields = ("client", "lead", "created_by")
    scoped_fk = _CLIENT_AND_LEAD

    class Media:
        """«Заявка» autocomplete фильтруется по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

    readonly_fields = (
        "direction",
        "from_email",
        "error_message",
        "created_at",
        "sent_at",
        "created_by",
        "message_id",
        "in_reply_to",
        "imap_uid",
        "mailbox",
        "received_at",
    )
    ordering = ("client__email", "-created_at")
    actions = ("queue_send",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "client",
                    "lead",
                    "direction",
                    "status",
                    "to_email",
                    "from_email",
                    "reply_to_email",
                    "subject",
                    "body",
                ),
            },
        ),
        (
            "Доставка",
            {
                "fields": ("error_message", "created_by", "created_at", "sent_at"),
            },
        ),
        (
            "Технические",
            {
                "fields": ("message_id", "in_reply_to", "imap_uid", "mailbox", "received_at"),
            },
        ),
    )

    @admin.display(description="ID", ordering="client__email")
    def client_email_id(self, obj: EmailMessage) -> str:
        """Group key: client email (fallback to to_email)."""
        if obj.client_id:
            return cast(Client, obj.client).email
        return (obj.to_email or "").strip().lower() or "—"

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailMessage]:
        """Prefetch client; scope rows for managers."""
        qs = super().get_queryset(request).select_related("client", "lead", "created_by")
        return scope_emails_for_manager(qs, request.user)

    @admin.action(description=_("Отправить выбранные (очередь)"), permissions=("change",))
    def queue_send(
        self,
        request: HttpRequest,
        queryset: Any,
    ) -> None:
        """Enqueue draft/failed messages (skip already queued/sent).

        Uses transaction.on_commit so Celery never races the DB commit.
        """
        from crm.services import enqueue_crm_email

        allowed = queryset.filter(
            status__in=(EmailStatus.DRAFT, EmailStatus.FAILED),
        )
        count = 0
        for msg in allowed:
            updated = EmailMessage.objects.filter(
                pk=msg.pk,
                status__in=(EmailStatus.DRAFT, EmailStatus.FAILED),
            ).update(status=EmailStatus.QUEUED)
            if not updated:
                continue
            enqueue_crm_email(msg.pk)
            count += 1
        skipped = queryset.count() - count
        self.message_user(
            request,
            _("В очередь: %(n)s. Пропущено: %(skip)s.") % {"n": count, "skip": skipped},
            messages.SUCCESS if count else messages.WARNING,
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: EmailMessage,
        form: Any,
        change: bool,
    ) -> None:
        """On create, set created_by; enqueue only on transition to QUEUED."""
        from crm.services import enqueue_crm_email

        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        lead = cast(Lead | None, obj.lead) if obj.lead_id else None
        if not lead_visible_to_manager(lead, request.user):
            raise PermissionDenied(_("Нельзя привязать письмо к чужой заявке."))
        previous_status = None
        if change and obj.pk:
            previous_status = EmailMessage.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        super().save_model(request, obj, form, change)
        became_queued = obj.status == EmailStatus.QUEUED and (not change or previous_status != EmailStatus.QUEUED)
        if became_queued:
            enqueue_crm_email(obj.pk)


@admin.register(EmailTemplate)
class EmailTemplateAdmin(ModelAdmin):
    """Reusable email presets: picked via «Шаблон» on compose forms."""

    list_display = ("name", "subject", "is_active", "sort_order", "updated_at")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "subject", "body")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("sort_order", "name")
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "is_active", "sort_order", "subject", "body"),
                "description": (
                    "Плейсхолдеры {имя}, {компания}, {почта}, {телефон} подставляются из карточки клиента или заявки."
                ),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(EmailAttachment)
class EmailAttachmentAdmin(ModelAdmin):
    """Attachment registry; files live in PRIVATE_MEDIA_ROOT (no public URL)."""

    list_display = ("email", "filename", "content_type", "size", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("filename", "email__subject", "email__from_email")
    readonly_fields = ("email", "filename", "content_type", "size", "file", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Attachments arrive via IMAP only."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailAttachment]:
        """Scope attachments to messages visible to the manager."""
        qs = super().get_queryset(request).select_related("email", "email__client")
        visible = scope_emails_for_manager(
            EmailMessage.objects.all(),
            request.user,
        ).values("pk")
        return qs.filter(email_id__in=visible)

    def get_urls(self) -> list[Any]:
        """Add scoped staff download endpoint."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/download/",
                self.admin_site.admin_view(self.download_view),
                name="crm_emailattachment_download",
            ),
        ]
        return custom + urls

    def download_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Serve the file only when the parent email is in manager scope."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(EmailAttachment, pk=pk)
        visible = scope_emails_for_manager(
            EmailMessage.objects.filter(pk=obj.email_id),
            request.user,
        ).exists()
        if not visible:
            raise PermissionDenied(_("Нет доступа к вложению этого письма."))
        return FileResponse(
            open(obj.file.path, "rb"),
            as_attachment=True,
            filename=obj.filename,
        )


@admin.register(InboundMailboxState)
class InboundMailboxStateAdmin(ModelAdmin):
    """IMAP cursor + fetch health (singleton; read-only for staff)."""

    list_display = ("folder", "last_uid", "last_run_at", "last_error")
    readonly_fields = ("folder", "last_uid", "last_run_at", "last_error")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Singleton row is created by the fetch task."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Cursor row must not be removed."""
        return False
