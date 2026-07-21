"""Django Admin for CRM: clients, activities, outbound email."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin
from crm.forms import ComposeEmailForm
from crm.models import Activity, Client, EmailMessage, EmailStatus
from crm.services import (
    create_outbound_email,
    scope_activities_for_manager,
    scope_clients_for_manager,
    scope_emails_for_manager,
)
from leads.models import Lead
from leads.services import lead_visible_to_manager, scope_leads_for_manager


def _scoped_lead_queryset(request: HttpRequest) -> QuerySet[Lead]:
    """Leads the current manager may attach to CRM rows."""
    return scope_leads_for_manager(Lead.objects.all(), request.user)


class LeadInline(TabularInline):
    """RFQ / consult requests on this client card (scoped for managers)."""

    model = Lead
    extra = 0
    fields = (
        "status",
        "lead_type",
        "name",
        "company",
        "message",
        "assignee",
        "created_at",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "заявка"
    verbose_name_plural = "заявки клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Leads arrive via public API / signal — not manual add on the card."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lead]:
        """Hide foreign leads that the manager cannot open in Lead Admin."""
        return scope_leads_for_manager(super().get_queryset(request), request.user)


class ActivityInline(TabularInline):
    """Timeline notes on a Client card."""

    model = Activity
    extra = 1
    fields = ("activity_type", "subject", "body", "lead", "author", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("lead",)
    show_change_link = True

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: HttpRequest,
        **kwargs: Any,
    ) -> Any:
        """Restrict lead FK to scoped rows (blocks visibility escalation)."""
        if db_field.name == "lead":
            kwargs["queryset"] = _scoped_lead_queryset(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EmailMessageInline(TabularInline):
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
class ClientAdmin(OpenChangeLinkMixin, ModelAdmin):
    """CRM client card: contacts, assignee, leads, timeline, send email.

    ID клиента = email. Несколько заявок с одним email попадают в одну
    карточку. Поиск/фильтры: email (ID), имя, компания.
    """

    list_display = (
        "email_id",
        "name",
        "company",
        "leads_count",
        "phone",
        "assignee",
        "is_active",
        "updated_at",
    )
    list_display_links = ("email_id", "name")
    list_filter = ("is_active", "assignee", "company", "updated_at")
    search_fields = ("email", "name", "company", "phone", "notes")
    autocomplete_fields = ("assignee",)
    readonly_fields = ("created_at", "updated_at", "leads_count")
    inlines = (LeadInline, ActivityInline, EmailMessageInline)
    ordering = ("email", "name", "company")
    fieldsets = (
        (
            "Контакт (ID = эл. почта)",
            {
                "fields": ("email", "name", "phone", "company", "is_active"),
                "description": (
                    "Одинаковый email (ID) = один клиент. Заявки с тем же ID "
                    "добавляются в эту карточку, новая карточка не создаётся."
                ),
            },
        ),
        (
            "Менеджер",
            {"fields": ("assignee", "notes")},
        ),
        (
            "Метаданные",
            {
                "fields": ("leads_count", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    change_form_template = "admin/crm/client/change_form.html"

    @admin.display(description="ID", ordering="email")
    def email_id(self, obj: Client) -> str:
        """Client ID is the email address (unique card key)."""
        return obj.email

    @admin.display(description="Заявок", ordering="_leads_count")
    def leads_count(self, obj: Client) -> int:
        """Number of leads attached to this card."""
        count = getattr(obj, "_leads_count", None)
        if count is not None:
            return int(count)
        return obj.leads.count()  # type: ignore[attr-defined]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Client]:
        """Annotate lead count; scope cards for non-superuser managers."""
        from django.db.models import Count

        qs = super().get_queryset(request).annotate(_leads_count=Count("leads", distinct=True))
        return scope_clients_for_manager(qs, request.user)

    def save_formset(
        self,
        request: HttpRequest,
        form: Any,
        formset: Any,
        change: bool,
    ) -> None:
        """Set author on new Activity rows; reject out-of-scope lead FKs."""
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, Activity):
                if obj.author_id is None:
                    obj.author = request.user
                lead = cast(Lead | None, obj.lead) if obj.lead_id else None
                if not lead_visible_to_manager(lead, request.user):
                    raise PermissionDenied(
                        _("Нельзя привязать активность к чужой заявке."),
                    )
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()

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
        if not self.has_change_permission(request):
            raise PermissionDenied
        client = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, client):
            raise PermissionDenied
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
class ActivityAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Standalone activity list (also edited via Client inline).

    ID = email клиента; строки с одним email идут группой.
    """

    list_display = (
        "client_email_id",
        "activity_type",
        "subject",
        "client",
        "lead",
        "author",
        "created_at",
    )
    list_display_links = ("subject",)
    list_filter = ("activity_type", "created_at")
    search_fields = ("subject", "body", "client__name", "client__email")
    autocomplete_fields = ("client", "lead", "author")
    readonly_fields = ("created_at",)
    ordering = ("client__email", "-created_at")

    @admin.display(description="ID", ordering="client__email")
    def client_email_id(self, obj: Activity) -> str:
        """Group key: client email (same ID → same client card)."""
        if not obj.client_id:
            return "—"
        return cast(Client, obj.client).email

    def get_queryset(self, request: HttpRequest) -> QuerySet[Activity]:
        """Prefetch relations; scope rows for managers."""
        qs = super().get_queryset(request).select_related("client", "lead", "author")
        return scope_activities_for_manager(qs, request.user)

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: HttpRequest,
        **kwargs: Any,
    ) -> Any:
        """Restrict client/lead pickers to scoped rows."""
        if db_field.name == "lead":
            kwargs["queryset"] = _scoped_lead_queryset(request)
        if db_field.name == "client":
            kwargs["queryset"] = scope_clients_for_manager(Client.objects.all(), request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(
        self,
        request: HttpRequest,
        obj: Activity,
        form: Any,
        change: bool,
    ) -> None:
        """Set author on create; reject out-of-scope lead FK."""
        if not change and obj.author_id is None:
            obj.author = request.user
        lead = cast(Lead | None, obj.lead) if obj.lead_id else None
        if not lead_visible_to_manager(lead, request.user):
            raise PermissionDenied(_("Нельзя привязать активность к чужой заявке."))
        super().save_model(request, obj, form, change)


@admin.register(EmailMessage)
class EmailMessageAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Outbound/inbound email log; staff can resend failed/draft.

    ID = email клиента (или to_email); одинаковые ID группируются.
    """

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
    readonly_fields = (
        "direction",
        "from_email",
        "error_message",
        "created_at",
        "sent_at",
        "created_by",
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

    def formfield_for_foreignkey(
        self,
        db_field: Any,
        request: HttpRequest,
        **kwargs: Any,
    ) -> Any:
        """Restrict client/lead pickers to scoped rows."""
        if db_field.name == "lead":
            kwargs["queryset"] = _scoped_lead_queryset(request)
        if db_field.name == "client":
            kwargs["queryset"] = scope_clients_for_manager(Client.objects.all(), request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.action(description=_("Отправить выбранные (очередь)"))
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
