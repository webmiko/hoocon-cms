"""Django Admin for CRM: clients, activities, outbound email."""

from __future__ import annotations

import logging
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, QuerySet
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from config.admin_mixins import OpenChangeLinkMixin, filter_autocomplete_by_client
from config.unfold_callbacks import _versioned_static
from crm.forms import ComposeEmailForm, SpecImportForm
from crm.mail_links import staff_reply_to_email
from crm.manager_signatures import manager_reply_signature
from crm.models import (
    Activity,
    Call,
    Client,
    ClientDocument,
    Company,
    CompanyMember,
    EmailAttachment,
    EmailMessage,
    EmailStatus,
    EmailTemplate,
    InboundMailboxState,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from crm.services import (
    create_outbound_email,
    email_template_context_for_client,
    get_active_email_template,
    render_email_template,
    scope_activities_for_manager,
    scope_clients_for_manager,
    scope_emails_for_manager,
)
from leads.models import Lead
from leads.services import lead_visible_to_manager, scope_leads_for_manager
from supportchat.models import Conversation

logger = logging.getLogger(__name__)


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

    def get_queryset(self, request: HttpRequest) -> QuerySet[Activity]:
        """Prefetch lead/author on the client card timeline."""
        return super().get_queryset(request).select_related("lead", "author")


class EmailMessageInline(TabularInline):
    """Recent emails on a Client card (read-mostly)."""

    model = EmailMessage
    extra = 0
    fields = (
        "direction",
        "status",
        "lead_link",
        "to_email",
        "subject",
        "created_at",
        "sent_at",
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True
    max_num = 20

    @admin.display(description="заявка")
    def lead_link(self, obj: EmailMessage) -> str:
        """Linked обращение — видно, к какой заявке относится письмо."""
        if obj.lead_id is None:
            return "—"
        url = reverse("admin:leads_lead_change", args=[obj.lead_id])
        return format_html('<a href="{}">#{}</a>', url, obj.lead_id)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Compose via «Написать письмо», not inline add."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[EmailMessage]:
        """Prefetch lead link on the client card inline."""
        return super().get_queryset(request).select_related("lead")


class ConversationInline(TabularInline):
    """Support chat dialogs linked to this client (read-mostly)."""

    model = Conversation
    extra = 0
    fields = (
        "channel",
        "status",
        "display_name",
        "contact_email",
        "staff_unread_count",
        "assignee",
        "last_message_at",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    max_num = 20
    ordering = (F("last_message_at").desc(nulls_last=True), "-id")
    verbose_name = "диалог поддержки"
    verbose_name_plural = "диалоги поддержки"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Conversations come from the widget/messengers, not manual add."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Conversation]:
        """Prefetch assignee for the inline rows."""
        return super().get_queryset(request).select_related("assignee")


class QuoteItemInline(TabularInline):
    """SKU lines of a quote (manager-editable)."""

    model = QuoteItem
    extra = 1
    fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
    autocomplete_fields = ("sku",)


class QuoteInline(TabularInline):
    """Quotes issued from this client card (read-mostly)."""

    model = Quote
    extra = 0
    fields = ("number", "status", "lead", "sent_at", "created_at")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "коммерческое предложение"
    verbose_name_plural = "коммерческие предложения"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """КП создаётся кнопкой «Создать КП» на заявке, не вручную здесь."""
        return False


class ClientDocumentInline(TabularInline):
    """Документы карточки (ЛК-3/14): КП-счёта-УПД, private download."""

    model = ClientDocument
    extra = 1
    fields = ("title", "kind", "file", "edo_status", "download_link", "created_at")
    readonly_fields = ("download_link", "created_at")
    ordering = ("-created_at",)
    verbose_name = "документ"
    verbose_name_plural = "документы"

    @admin.display(description="файл")
    def download_link(self, obj: ClientDocument) -> str:
        """Staff download link through the scoped admin view."""
        if not obj.pk:
            return "—"
        url = reverse("admin:crm_clientdocument_download", args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.title or "файл")


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
    readonly_fields = ("created_at", "updated_at", "leads_count", "company_key")
    inlines = (
        LeadInline,
        ActivityInline,
        EmailMessageInline,
        ConversationInline,
        QuoteInline,
        ClientDocumentInline,
    )
    ordering = ("email", "name", "company")
    actions = ("merge_clients_action",)
    fieldsets = (
        (
            "Контакт (ID = эл. почта)",
            {
                "fields": ("email", "name", "phone", "company", "is_active"),
                "description": (
                    "Одинаковая эл. почта (ID) = один клиент. Заявки с тем же ID "
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
                "fields": ("leads_count", "company_key", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )
    change_form_template = "admin/crm/client/change_form.html"

    @admin.display(description="ID", ordering="email")
    def email_id(self, obj: Client) -> str:
        """Client ID is the email address (unique card key)."""
        return obj.email

    @admin.action(
        description="Объединить карточки (связи перейдут на основную)",
    )
    def merge_clients_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[Client],
    ) -> None:
        """Merge selected duplicate cards (same company_key or ручной выбор).

        Целевая карточка — та, что с аккаунтом ЛК, иначе самая ранняя по
        дате создания. Связи источников переносятся; источники
        деактивируются, а не удаляются (email-ы остаются уникальными).
        """
        clients = list(queryset.order_by("created_at", "pk"))
        if len(clients) < 2:
            self.message_user(
                request,
                _("Выберите хотя бы две карточки для объединения."),
                messages.WARNING,
            )
            return
        with_account = [c for c in clients if c.account_id]
        target = with_account[0] if with_account else clients[0]
        sources = [c for c in clients if c.pk != target.pk]
        from crm.services import merge_clients

        moved = merge_clients(target, sources, actor=request.user)
        total = sum(moved.values())
        self.message_user(
            request,
            _(
                "Карточки объединены в %(target)s: перенесено %(total)s связей "
                "(заявки %(leads)s, письма %(emails)s, КП %(quotes)s, "
                "заказы %(orders)s). Источники деактивированы."
            )
            % {
                "target": target.email,
                "total": total,
                "leads": moved["leads"],
                "emails": moved["emails"],
                "quotes": moved["quotes"],
                "orders": moved["orders"],
            },
            messages.SUCCESS,
        )

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

        qs = (
            super()
            .get_queryset(request)
            .select_related("assignee")
            .annotate(_leads_count=Count("leads", distinct=True))
        )
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
            path(
                "<path:object_id>/import-spec/",
                self.admin_site.admin_view(self.import_spec_view),
                name=f"{info[0]}_{info[1]}_import_spec",
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
        extra_context["import_spec_url"] = reverse(
            "admin:crm_client_import_spec",
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
        template = get_active_email_template(request.GET.get("template"))

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
            initial: dict[str, Any] = {
                "to_email": client.email,
                "subject": "",
                "body": "",
                "send_now": True,
            }
            if template is not None:
                initial["subject"], initial["body"] = render_email_template(
                    template,
                    context=email_template_context_for_client(client),
                )
            form = ComposeEmailForm(initial=initial)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": client,
            "title": _("Написать письмо: %(name)s") % {"name": client.name},
            "form": form,
            "media": self.media,
            "email_templates": EmailTemplate.objects.filter(is_active=True).only("pk", "name"),
            "selected_template_id": template.pk if template else None,
        }
        return render(request, "admin/crm/compose_email.html", context)

    def import_spec_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """Upload .xlsx spec → draft RFQ lead with resolved positions (ЛК-9)."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        client = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, client):
            raise PermissionDenied
        if not request.user.has_perm("leads.add_lead"):
            raise PermissionDenied
        change_url = reverse("admin:crm_client_change", args=[client.pk])

        if request.method == "POST":
            form = SpecImportForm(request.POST, request.FILES)
            if form.is_valid():
                from cabinet.spec_import import (
                    SpecParseError,
                    create_lead_from_spec_rows,
                    parse_spec_xlsx,
                )

                uploaded = form.cleaned_data["file"]
                try:
                    rows = parse_spec_xlsx(uploaded)
                except SpecParseError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                    return HttpResponseRedirect(change_url)
                lead = create_lead_from_spec_rows(
                    rows,
                    client=client,
                    source_name=uploaded.name,
                )
                resolved = sum(1 for r in rows if r.sku is not None)
                analogs = sum(1 for r in rows if r.via_analog)
                self.message_user(
                    request,
                    _(
                        "Создана заявка #%(id)s: %(total)s позиций "
                        "(нашлось %(resolved)s, из них по аналогам %(analogs)s)."
                    )
                    % {
                        "id": lead.pk,
                        "total": len(rows),
                        "resolved": resolved,
                        "analogs": analogs,
                    },
                    messages.SUCCESS,
                )
                return HttpResponseRedirect(
                    reverse("admin:leads_lead_change", args=[lead.pk]),
                )
        else:
            form = SpecImportForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": client,
            "title": _("Импорт спецификации: %(name)s") % {"name": client.name},
            "form": form,
            "media": self.media,
        }
        return render(request, "admin/crm/import_spec.html", context)


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

    class Media:
        """«Заявка» autocomplete фильтруется по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

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
class EmailMessageAdmin(OpenChangeLinkMixin, ModelAdmin):
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


class QuoteAdminForm(forms.ModelForm):
    """«Заявка» КП должна принадлежать выбранному клиенту."""

    class Meta:
        model = Quote
        fields = "__all__"

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        lead = cast(Lead | None, cleaned.get("lead"))
        client = cast(Client | None, cleaned.get("client"))
        if lead and client and lead.client_id and lead.client_id != client.pk:
            self.add_error(
                "lead",
                ValidationError(
                    _("Заявка #%s привязана к другому клиенту.") % lead.pk,
                ),
            )
        return cleaned


@admin.register(Quote)
class QuoteAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Коммерческие предложения: позиции, статус, связь с заявкой."""

    form = QuoteAdminForm
    list_display = ("number", "client", "lead", "status", "created_at", "sent_at")
    list_display_links = ("number", "client")
    list_filter = ("status", "created_at")
    search_fields = (
        "number",
        "client__email",
        "client__name",
        "client__company",
        "items__sku_code",
    )
    autocomplete_fields = ("client", "lead", "created_by")
    readonly_fields = ("number", "sent_at", "created_at", "updated_at")
    inlines = (QuoteItemInline,)

    class Media:
        """«Заявка» autocomplete фильтруется по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Quote]:
        """Autocomplete поля «КП» (документ/заказ) — только КП клиента."""
        return filter_autocomplete_by_client(request, super().get_queryset(request))

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "number",
                    "status",
                    "client",
                    "lead",
                    "created_by",
                    "comment",
                ),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("sent_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(
        self,
        request: HttpRequest,
        obj: Quote,
        form: Any,
        change: bool,
    ) -> None:
        """Status SENT stamps sent_at, issues the PDF doc and closes the lead."""
        super().save_model(request, obj, form, change)
        if obj.status == QuoteStatus.SENT:
            first_issue = obj.sent_at is None
            if first_issue:
                obj.sent_at = timezone.now()
                obj.save(update_fields=["sent_at", "updated_at"])
            self._issue_quote_document(request, obj, notify=first_issue)
            self._close_source_lead(request, obj)
        elif obj.sent_at is not None:
            obj.sent_at = None
            obj.save(update_fields=["sent_at", "updated_at"])

    def _issue_quote_document(
        self,
        request: HttpRequest,
        obj: Quote,
        *,
        notify: bool,
    ) -> None:
        """PDF → ClientDocument (private); клиенту — письмо-уведомление.

        Notification fires only on the first SENT transition (re-saves of
        an already-issued quote refresh the PDF but do not re-mail).
        """
        from crm.quote_docs import ensure_quote_pdf_document, notify_quote_issued

        try:
            document = ensure_quote_pdf_document(obj)
        except Exception as exc:  # PDF failure must not block the save
            logger.exception("quote_pdf_failed quote_id=%s", obj.pk)
            self.message_user(
                request,
                f"КП выдано, но PDF не сформирован: {type(exc).__name__}",
                messages.WARNING,
            )
            return
        client = cast(Client, obj.client)
        if notify and client.email:
            author = request.user if request.user.is_authenticated else None
            notify_quote_issued(obj, author=author, document=document)

    def _close_source_lead(self, request: HttpRequest, obj: Quote) -> None:
        """Выданное КП закрывает заявку результатом (не «просто done»)."""
        lead = cast(Lead | None, obj.lead)
        if lead is None or lead.status == Lead.LeadStatus.DONE:
            return
        from leads.services import set_lead_status

        updated, error = set_lead_status(
            lead,
            status=Lead.LeadStatus.DONE,
            actor=request.user,
        )
        if error:
            self.message_user(
                request,
                f"КП выдано, но заявку #{lead.pk} закрыть не удалось: {error}",
                messages.WARNING,
            )
        else:
            self.message_user(
                request,
                f"Заявка #{updated.pk} закрыта результатом «{obj.number}».",
                messages.SUCCESS,
            )


@admin.register(ClientDocument)
class ClientDocumentAdmin(ModelAdmin):
    """Документы клиента: upload в карточке или здесь; private download."""

    list_display = ("title", "client", "kind", "edo_status", "created_at")
    list_filter = ("kind", "edo_status", "created_at")
    search_fields = ("title", "client__email", "client__company")
    autocomplete_fields = ("client", "quote", "order")
    list_select_related = ("client",)
    readonly_fields = ("created_at",)

    class Media:
        """«КП»/«Заказ» autocomplete фильтруются по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

    def get_queryset(self, request: HttpRequest) -> QuerySet[ClientDocument]:
        """Scope documents to clients visible to the manager."""
        qs = super().get_queryset(request)
        visible = scope_clients_for_manager(
            Client.objects.all(),
            request.user,
        ).values("pk")
        return qs.filter(client_id__in=visible)

    def save_model(self, request: HttpRequest, obj: ClientDocument, form: Any, change: bool) -> None:
        """Stamp uploader on first save."""
        if not change and not obj.uploaded_by_id:
            obj.uploaded_by = request.user  # type: ignore[misc]
        super().save_model(request, obj, form, change)

    def get_urls(self) -> list[Any]:
        """Scoped staff download endpoint."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/download/",
                self.admin_site.admin_view(self.download_view),
                name="crm_clientdocument_download",
            ),
        ]
        return custom + urls

    def download_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Serve the file only when the client is in manager scope."""
        obj = get_object_or_404(ClientDocument, pk=pk)
        visible = scope_clients_for_manager(
            Client.objects.filter(pk=obj.client_id),
            request.user,
        ).exists()
        if not visible:
            raise PermissionDenied(_("Нет доступа к документу этого клиента."))
        return FileResponse(
            obj.file.open("rb"),
            as_attachment=True,
            filename=obj.title or str(obj.file.name or "document"),
        )


class CompanyMemberInline(TabularInline):
    """Members of a company card (CRM-x)."""

    model = CompanyMember
    extra = 1
    fields = ("client", "account", "role")
    autocomplete_fields = ("client",)


@admin.register(Company)
class CompanyAdmin(ModelAdmin):
    """Карточка юрлица: реквизиты + члены (целевая схема CRM-x)."""

    list_display = ("name", "inn", "members_count", "clients_count", "updated_at")
    search_fields = ("name", "inn")
    readonly_fields = ("company_key", "created_at", "updated_at")
    inlines = (CompanyMemberInline,)

    @admin.display(description="сотрудников")
    def members_count(self, obj: Company) -> int:
        return obj.members.count()

    @admin.display(description="карточек")
    def clients_count(self, obj: Company) -> int:
        return obj.clients.count()
