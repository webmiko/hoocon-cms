"""Django Admin for CRM: clients, activities, outbound email."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from crm.forms import ComposeEmailForm
from crm.models import Activity, Client, EmailMessage, EmailStatus
from crm.services import create_outbound_email
from crm.tasks import send_crm_email


class ActivityInline(admin.TabularInline):
    """Timeline notes on a Client card."""

    model = Activity
    extra = 1
    fields = ("activity_type", "subject", "body", "lead", "author", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("lead",)
    show_change_link = True


class EmailMessageInline(admin.TabularInline):
    """Recent emails on a Client card (read-mostly)."""

    model = EmailMessage
    extra = 0
    fields = (
        "direction",
        "status",
        "to_email",
        "subject",
        "created_at",
        "sent_at",
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True
    max_num = 20

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Compose via «Написать письмо», not inline add."""
        return False


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    """CRM client card: contacts, assignee, timeline, send email."""

    list_display = (
        "name",
        "company",
        "email",
        "phone",
        "assignee",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "assignee", "updated_at")
    search_fields = ("name", "email", "company", "phone", "notes")
    autocomplete_fields = ("assignee",)
    readonly_fields = ("created_at", "updated_at")
    inlines = (ActivityInline, EmailMessageInline)
    ordering = ("-updated_at",)
    fieldsets = (
        (
            "Контакт",
            {"fields": ("name", "email", "phone", "company", "is_active")},
        ),
        (
            "Менеджер",
            {"fields": ("assignee", "notes")},
        ),
        (
            "Метаданные",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    change_form_template = "admin/crm/client/change_form.html"

    def get_urls(self) -> list:
        """Add compose-email URL for the change-form button."""
        urls = super().get_urls()
        info = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                "<path:object_id>/compose-email/",
                self.admin_site.admin_view(self.compose_email_view),
                name=f"{info[0]}_{info[1]}_compose_email",
            ),
        ]
        return custom + urls

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Inject compose-email URL into the change form template."""
        extra_context = extra_context or {}
        extra_context["compose_email_url"] = reverse(
            "admin:crm_client_compose_email",
            args=[object_id],
        )
        return super().change_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )

    def compose_email_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """Form to compose and queue an outbound email to this Client."""
        client = get_object_or_404(Client, pk=object_id)
        change_url = reverse("admin:crm_client_change", args=[client.pk])

        if request.method == "POST":
            form = ComposeEmailForm(request.POST)
            if form.is_valid():
                author = request.user if request.user.is_authenticated else None
                msg = create_outbound_email(
                    client=client,
                    subject=form.cleaned_data["subject"],
                    body=form.cleaned_data["body"],
                    to_email=form.cleaned_data["to_email"],
                    author=author if author and not author.is_anonymous else None,
                    send_now=bool(form.cleaned_data.get("send_now")),
                )
                if msg.status == EmailStatus.QUEUED:
                    self.message_user(
                        request,
                        _("Письмо поставлено в очередь на отправку."),
                        messages.SUCCESS,
                    )
                else:
                    self.message_user(
                        request,
                        _("Черновик сохранён. Отправьте из раздела «Письма»."),
                        messages.INFO,
                    )
                return HttpResponseRedirect(change_url)
        else:
            form = ComposeEmailForm(
                initial={
                    "to_email": client.email,
                    "subject": "",
                    "body": "",
                    "send_now": True,
                },
            )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": client,
            "title": _("Написать письмо: %(name)s") % {"name": client.name},
            "form": form,
            "media": self.media,
        }
        return render(request, "admin/crm/compose_email.html", context)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    """Standalone activity list (also edited via Client inline)."""

    list_display = (
        "id",
        "activity_type",
        "subject",
        "client",
        "lead",
        "author",
        "created_at",
    )
    list_filter = ("activity_type", "created_at")
    search_fields = ("subject", "body", "client__name", "client__email")
    autocomplete_fields = ("client", "lead", "author")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    def save_model(
        self,
        request: HttpRequest,
        obj: Activity,
        form: Any,
        change: bool,
    ) -> None:
        """Set author to current staff user when creating."""
        if not change and obj.author_id is None:
            obj.author = request.user
        super().save_model(request, obj, form, change)


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    """Outbound/inbound email log; staff can resend failed/draft."""

    list_display = (
        "id",
        "direction",
        "status",
        "to_email",
        "subject",
        "client",
        "created_at",
        "sent_at",
    )
    list_filter = ("direction", "status", "created_at")
    search_fields = ("subject", "to_email", "from_email", "client__name", "body")
    autocomplete_fields = ("client", "lead", "created_by")
    readonly_fields = (
        "direction",
        "from_email",
        "error_message",
        "created_at",
        "sent_at",
        "created_by",
    )
    ordering = ("-created_at",)
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
    )

    @admin.action(description=_("Отправить выбранные (очередь)"))
    def queue_send(
        self,
        request: HttpRequest,
        queryset: Any,
    ) -> None:
        """Enqueue draft/failed/queued messages for Celery send."""
        allowed = queryset.exclude(status=EmailStatus.SENT)
        count = 0
        for msg in allowed:
            EmailMessage.objects.filter(pk=msg.pk).update(status=EmailStatus.QUEUED)
            send_crm_email.delay(msg.pk)
            count += 1
        skipped = queryset.count() - count
        self.message_user(
            request,
            _("В очередь: %(n)s. Уже отправленных пропущено: %(skip)s.") % {"n": count, "skip": skipped},
            messages.SUCCESS if count else messages.WARNING,
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: EmailMessage,
        form: Any,
        change: bool,
    ) -> None:
        """On create, set created_by; queue if status is QUEUED."""
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        if obj.status == EmailStatus.QUEUED:
            send_crm_email.delay(obj.pk)
