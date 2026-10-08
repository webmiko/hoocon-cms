"""Django Admin for CRM: clients, activities, outbound email."""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F, QuerySet
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from cabinet.models import Order, RmaCase
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
    scope_calls_for_manager,
    scope_clients_for_manager,
    scope_emails_for_manager,
    scope_quotes_for_manager,
)
from leads.models import Lead
from leads.services import lead_visible_to_manager, scope_leads_for_manager
from supportchat.models import Conversation

logger = logging.getLogger(__name__)


def _scoped_lead_queryset(request: HttpRequest) -> QuerySet[Lead]:
    """Leads the current manager may attach to CRM rows."""
    return scope_leads_for_manager(Lead.objects.all(), request.user)


class OverdueNextContactFilter(admin.SimpleListFilter):
    """Clients whose next-contact reminder is in the past."""

    title = _("следующий контакт")
    parameter_name = "next_contact_overdue"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        """Single overdue option."""
        del request, model_admin
        return [("yes", "Просрочен")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Client]) -> QuerySet[Client]:
        """Keep cards with next_contact_at in the past."""
        del request
        if self.value() != "yes":
            return queryset
        return queryset.filter(
            next_contact_at__isnull=False,
            next_contact_at__lt=timezone.now(),
        )


class OrderInline(TabularInline):
    """Orders on the client card (cabinet.Order)."""

    tab = True
    model = Order
    extra = 0
    fields = ("number", "status", "progress", "planned_ship_date", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "заказ"
    verbose_name_plural = "заказы клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Заказ создаётся из КП, не вручную на карточке."""
        return False


class RmaCaseInline(TabularInline):
    """RMA cases on the client card."""

    tab = True
    model = RmaCase
    extra = 0
    fields = ("subject", "status", "serial_number", "created_at")
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "рекламация"
    verbose_name_plural = "рекламации клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Рекламации приходят из ЛК."""
        return False


class LeadInline(TabularInline):
    """RFQ / consult requests on this client card (scoped for managers)."""

    tab = True
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

    tab = True
    model = Activity
    extra = 0
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

    tab = True
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

    tab = True
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
    extra = 0
    fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
    autocomplete_fields = ("sku",)


class QuoteInline(TabularInline):
    """Quotes issued from this client card (read-mostly)."""

    tab = True
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


class CallInline(TabularInline):
    """Mango telephony log on the client card (read-only)."""

    tab = True
    model = Call
    extra = 0
    fields = (
        "direction",
        "state",
        "from_number",
        "to_number",
        "extension",
        "talk_duration",
        "started_at",
    )
    readonly_fields = fields
    show_change_link = True
    can_delete = False
    ordering = ("-started_at", "-id")
    verbose_name = "звонок"
    verbose_name_plural = "звонки клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Calls arrive via Mango webhook — not manual add on the card."""
        return False


class ClientDocumentInline(TabularInline):
    """Документы карточки (ЛК-3/14): КП-счёта-УПД, private download."""

    tab = True
    model = ClientDocument
    extra = 0
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
        "next_contact_at",
        "is_active",
        "updated_at",
    )
    list_display_links = ("email_id", "name")
    list_filter = (
        "is_active",
        "assignee",
        "company",
        OverdueNextContactFilter,
        "updated_at",
    )
    search_fields = ("email", "name", "company", "phone", "phone_digits", "notes", "company_ref__inn")
    autocomplete_fields = ("assignee", "company_ref")
    readonly_fields = (
        "created_at",
        "updated_at",
        "leads_count",
        "company_key",
        "card_summary",
        "colleagues_html",
    )
    inlines = (
        LeadInline,
        ActivityInline,
        CallInline,
        EmailMessageInline,
        ConversationInline,
        QuoteInline,
        OrderInline,
        RmaCaseInline,
        ClientDocumentInline,
    )
    ordering = ("email", "name", "company")
    actions = ("merge_clients_action",)

    class Media:
        """Inline «Написать»/«Позвонить» buttons next to email/phone inputs."""

        js = (_versioned_static("admin/js/hoocon-client-quick-actions.js"),)

    fieldsets = (
        (
            "Контакт (ID = эл. почта)",
            {
                "fields": (
                    "email",
                    "name",
                    "phone",
                    "company",
                    "company_ref",
                    "is_active",
                ),
                "description": (
                    "Одинаковая эл. почта (ID) = один клиент. Заявки с тем же ID "
                    "добавляются в эту карточку, новая карточка не создаётся."
                ),
            },
        ),
        (
            "Менеджер",
            {"fields": ("assignee", "next_contact_at", "notes")},
        ),
        (
            "Сводка и коллеги",
            {"fields": ("card_summary", "colleagues_html")},
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

    @admin.display(description="сводка")
    def card_summary(self, obj: Client) -> str:
        """Counts + similar-card warning for the change form."""
        if not obj.pk:
            return "—"
        from crm.company import similar_clients
        from crm.models import QuoteStatus as QStatus

        quotes = obj.quotes.all()
        open_q = quotes.filter(status__in=(QStatus.DRAFT, QStatus.SENT)).count()
        orders_n = obj.orders.count()
        rma_n = obj.rma_cases.count()
        similar = list(similar_clients(obj)[:5])
        overdue = bool(obj.next_contact_at and obj.next_contact_at < timezone.now())
        bits = [
            f"заявок {obj.leads.count()}",
            f"КП {quotes.count()} (открытых {open_q})",
            f"заказов {orders_n}",
            f"рекламаций {rma_n}",
        ]
        if overdue:
            bits.append("просрочен следующий контакт")
        summary = format_html("{}", " · ".join(bits))
        if not similar:
            return summary
        links = format_html_join(
            ", ",
            '<a href="{}">{}</a>',
            (
                (
                    reverse("admin:crm_client_change", args=[row.pk]),
                    row.email,
                )
                for row in similar
            ),
        )
        return format_html("{}<br>Похожие карточки: {}", summary, links)

    @admin.display(description="коллеги")
    def colleagues_html(self, obj: Client) -> str:
        """Other contacts of the same company."""
        if not obj.pk:
            return "—"
        from crm.company import colleague_clients

        rows = list(colleague_clients(obj)[:12])
        if not rows:
            return "—"
        return format_html_join(
            "<br>",
            '<a href="{}">{}</a> — {}',
            (
                (
                    reverse("admin:crm_client_change", args=[row.pk]),
                    row.email,
                    row.name,
                )
                for row in rows
            ),
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
            .select_related("assignee", "company_ref")
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
                "sales-report/",
                self.admin_site.admin_view(self.sales_report_view),
                name=f"{info[0]}_{info[1]}_sales_report",
            ),
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
            path(
                "<path:object_id>/import-spec/template/",
                self.admin_site.admin_view(self.import_spec_template_view),
                name=f"{info[0]}_{info[1]}_import_spec_template",
            ),
            path(
                "<path:object_id>/call-client/",
                self.admin_site.admin_view(self.call_client_view),
                name=f"{info[0]}_{info[1]}_call_client",
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
        extra_context["call_client_url"] = reverse(
            "admin:crm_client_call_client",
            args=[object_id],
        )
        extra_context["sales_report_url"] = reverse("admin:crm_client_sales_report")
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
                    reply_to_email=staff_reply_to_email(author),
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

        manager_email = staff_reply_to_email(request.user if request.user.is_authenticated else None)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": client,
            "title": _("Написать письмо: %(name)s") % {"name": client.name},
            "form": form,
            "media": self.media,
            "manager_reply_to_email": manager_email,
            "manager_signature_preview": manager_reply_signature(manager_email),
            "client_change_url": change_url,
            "email_templates": EmailTemplate.objects.filter(is_active=True).only("pk", "name"),
            "selected_template_id": template.pk if template else None,
        }
        return render(request, "admin/crm/compose_email.html", context)

    def sales_report_view(self, request: HttpRequest) -> HttpResponse:
        """РОП: воронка менеджеров за 7/30 дней (менеджер видит только себя)."""
        if not request.user.has_perm("crm.view_client"):
            raise PermissionDenied
        raw_days = request.GET.get("days", "7")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 7
        if days not in {7, 30, 0}:
            days = 7
        since = None if days <= 0 else timezone.now() - timedelta(days=days)
        from crm.reports import build_sales_report

        report = build_sales_report(since=since, user=request.user)
        context = {
            **self.admin_site.each_context(request),
            "title": "Отчёт по менеджерам",
            "report": report,
            "days": days,
            "opts": self.opts,
            "changelist_url": reverse("admin:crm_client_changelist"),
        }
        return render(request, "admin/crm/sales_report.html", context)

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
            "client_change_url": change_url,
            "spec_template_url": reverse(
                "admin:crm_client_import_spec_template",
                args=[client.pk],
            ),
        }
        return render(request, "admin/crm/import_spec.html", context)

    def import_spec_template_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """Download a starter .xlsx spec template (ЛК-9 helper)."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        client = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, client):
            raise PermissionDenied
        if not request.user.has_perm("leads.add_lead"):
            raise PermissionDenied
        from cabinet.spec_import import build_spec_template_xlsx

        response = HttpResponse(
            build_spec_template_xlsx(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="hoocon-spec-template.xlsx"'
        return response

    def call_client_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        """Click-to-call: Mango callback менеджер (добавочный) → клиент."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        client = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, client):
            raise PermissionDenied
        change_url = reverse("admin:crm_client_change", args=[client.pk])

        from crm.mango import (
            initiate_callback,
            initiate_callback_webhook,
            mango_configured,
            webhook_callback_configured,
        )

        extension = ""
        profile = getattr(request.user, "vpbx_profile", None)
        if profile is not None:
            extension = profile.extension if profile.is_enabled else ""
        blockers: list[str] = []
        use_api = mango_configured()
        if not use_api and not webhook_callback_configured():
            blockers.append(
                str(_("Mango не настроен: нет ни MANGO_VPBX_API_KEY/SALT, ни MANGO_CALLBACK_WEBHOOK_URL."))
            )
        if not extension:
            blockers.append(
                str(
                    _(
                        "У вас не задан добавочный Mango — укажите его в профиле "
                        "пользователя («Добавочный сотрудника»)."
                    )
                )
            )
        if not client.phone:
            blockers.append(str(_("У клиента не заполнен телефон.")))

        if request.method == "POST" and not blockers:
            try:
                if use_api:
                    result = initiate_callback(extension, client.phone)
                else:
                    initiate_callback_webhook(extension, client.phone)
                    result = {}
            except RuntimeError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.message_user(
                    request,
                    _("Вызов инициирован: Mango соединит ваш добавочный %(ext)s с %(phone)s.")
                    % {"ext": extension, "phone": client.phone},
                    messages.SUCCESS,
                )
                logger.info(
                    "mango_callback_initiated user=%s client=%s result=%s",
                    request.user.pk,
                    client.pk,
                    result.get("result"),
                )
            return HttpResponseRedirect(change_url)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "original": client,
            "title": _("Позвонить клиенту: %(name)s") % {"name": client.name or client.email},
            "blockers": blockers,
            "extension": extension,
            "client_change_url": change_url,
        }
        return render(request, "admin/crm/call_client.html", context)


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
    list_display = (
        "number",
        "client",
        "lead",
        "status_badge",
        "valid_until",
        "created_at",
        "sent_at",
    )
    list_display_links = ("number", "client")
    list_filter = ("status", "created_at")
    change_list_template = "admin/crm/quote/change_list.html"
    change_form_template = "admin/crm/quote/change_form.html"
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
        """Chained «Заявка» + канбан статусов КП."""

        js = (
            _versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),
            _versioned_static("admin/js/hoocon-admin-quotes-board.js"),
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Quote]:
        """Scope quotes to visible clients; autocomplete may further filter by ?client=."""
        qs = super().get_queryset(request).select_related("client", "lead", "created_by")
        qs = scope_quotes_for_manager(qs, request.user)
        return filter_autocomplete_by_client(request, qs)

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
                    "valid_until",
                    "vat_rate",
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

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Quote) -> str:
        """Colored status tag for wall/kanban (same CSS as leads)."""
        return format_html(
            '<span class="hoocon-lead-status hoocon-lead-status--{}">{}</span>',
            obj.status,
            obj.get_status_display(),
        )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict | None = None,
    ) -> HttpResponse:
        """Wall/kanban toggle; ``view`` is session-backed like leads."""
        extra = dict(extra_context or {})
        extra["hoocon_sales_report_url"] = reverse("admin:crm_client_sales_report")
        original = request.GET.copy()
        raw_view = (original.get("view") or "").strip().lower()
        if raw_view in {"wall", "kanban"}:
            view = raw_view
            request.session["hoocon_quote_view"] = view
        else:
            view = (request.session.get("hoocon_quote_view") or "wall").strip().lower()
            if view not in {"wall", "kanban"}:
                view = "wall"
        filter_params = original.copy()
        filter_params.pop("view", None)
        wall_params = filter_params.copy()
        wall_params["view"] = "wall"
        kanban_params = filter_params.copy()
        kanban_params["view"] = "kanban"
        extra["hoocon_quote_view"] = view
        extra["hoocon_quote_view_wall_url"] = f"?{wall_params.urlencode()}"
        extra["hoocon_quote_view_kanban_url"] = f"?{kanban_params.urlencode()}"
        request.GET = filter_params  # type: ignore[assignment]
        return super().changelist_view(request, extra_context=extra)

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Inject duplicate / create-order POST URLs."""
        extra_context = extra_context or {}
        extra_context["quote_duplicate_url"] = reverse(
            "admin:crm_quote_duplicate",
            args=[object_id],
        )
        extra_context["quote_create_order_url"] = reverse(
            "admin:crm_quote_create_order",
            args=[object_id],
        )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self) -> list:
        """Kanban set-status + duplicate + order-from-quote."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/set-status/",
                self.admin_site.admin_view(self.set_status_view),
                name="crm_quote_set_status",
            ),
            path(
                "<path:object_id>/duplicate/",
                self.admin_site.admin_view(self.duplicate_view),
                name="crm_quote_duplicate",
            ),
            path(
                "<path:object_id>/create-order/",
                self.admin_site.admin_view(self.create_order_view),
                name="crm_quote_create_order",
            ),
        ]
        return custom + urls

    def set_status_view(self, request: HttpRequest, object_id: int) -> JsonResponse:
        """JSON status update for КП kanban drag-and-drop."""
        if request.method != "POST":
            return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)
        if not request.user.has_perm("crm.change_quote"):
            raise PermissionDenied
        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)
        status = str(payload.get("status") or "").strip()
        if status not in QuoteStatus.values:
            return JsonResponse({"ok": False, "error": "invalid_status"}, status=400)
        quote = get_object_or_404(self.get_queryset(request), pk=object_id)
        quote.status = status
        quote.save(update_fields=["status", "updated_at"])
        from crm.quote_ops import finalize_quote_status

        finalize_quote_status(quote, actor=request.user)
        return JsonResponse({"ok": True, "status": quote.status})

    def duplicate_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """POST: copy КП into a new draft."""
        change_url = reverse("admin:crm_quote_change", args=[object_id])
        if request.method != "POST":
            return HttpResponseRedirect(change_url)
        if not request.user.has_perm("crm.add_quote"):
            raise PermissionDenied
        quote = get_object_or_404(self.get_queryset(request), pk=object_id)
        from crm.quote_ops import duplicate_quote

        copy = duplicate_quote(quote, author=request.user)
        self.message_user(request, _(f"Создан черновик {copy.number}."), messages.SUCCESS)
        return HttpResponseRedirect(reverse("admin:crm_quote_change", args=[copy.pk]))

    def create_order_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """POST: заказ из позиций КП."""
        change_url = reverse("admin:crm_quote_change", args=[object_id])
        if request.method != "POST":
            return HttpResponseRedirect(change_url)
        if not request.user.has_perm("cabinet.add_order"):
            raise PermissionDenied
        quote = get_object_or_404(self.get_queryset(request), pk=object_id)
        from crm.quote_ops import create_order_from_quote

        order, created = create_order_from_quote(quote)
        if created:
            self.message_user(
                request,
                _(f"Заказ {order.number} создан из {quote.number}."),
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _(f"Заказ {order.number} уже есть у этого КП."),
                messages.INFO,
            )
        return HttpResponseRedirect(reverse("admin:cabinet_order_change", args=[order.pk]))

    def save_model(
        self,
        request: HttpRequest,
        obj: Quote,
        form: Any,
        change: bool,
    ) -> None:
        """First SENT transition stamps sent_at, issues PDF and closes the lead."""
        super().save_model(request, obj, form, change)
        from crm.quote_ops import finalize_quote_status

        result = finalize_quote_status(obj, actor=request.user)
        if result["pdf_error"]:
            self.message_user(
                request,
                f"КП выдано, но PDF не сформирован: {result['pdf_error']}",
                messages.WARNING,
            )
        if result["lead_error"]:
            lead = cast("Lead | None", obj.lead)
            pk = lead.pk if lead is not None else "?"
            self.message_user(
                request,
                f"КП выдано, но заявку #{pk} закрыть не удалось: {result['lead_error']}",
                messages.WARNING,
            )
        elif result["lead_closed"]:
            self.message_user(
                request,
                f"Заявка #{result['lead_closed']} закрыта результатом «{obj.number}».",
                messages.SUCCESS,
            )


@admin.register(ClientDocument)
class ClientDocumentAdmin(OpenChangeLinkMixin, ModelAdmin):
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
class CompanyAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Карточка юрлица: реквизиты + члены (целевая схема CRM-x)."""

    list_display = ("name", "inn", "members_count", "clients_count", "updated_at")
    list_display_links = ("name",)
    search_fields = ("name", "inn")
    readonly_fields = ("company_key", "created_at", "updated_at")
    inlines = (CompanyMemberInline,)
    actions = ("merge_companies_action",)

    @admin.action(description="Объединить компании (карточки перейдут на основную)")
    def merge_companies_action(
        self,
        request: HttpRequest,
        queryset: QuerySet[Company],
    ) -> None:
        """Merge selected legal entities into the oldest row."""
        companies = list(queryset.order_by("created_at", "pk"))
        if len(companies) < 2:
            self.message_user(
                request,
                _("Выберите хотя бы две компании для объединения."),
                messages.WARNING,
            )
            return
        target = companies[0]
        sources = companies[1:]
        from crm.company import merge_companies

        moved = merge_companies(target, sources, actor=request.user)
        self.message_user(
            request,
            _("Компании объединены в «%(name)s»: карточек %(clients)s, сотрудников %(members)s.")
            % {
                "name": target.name,
                "clients": moved["clients"],
                "members": moved["members"],
            },
            messages.SUCCESS,
        )

    @admin.display(description="сотрудников", ordering="_members_count")
    def members_count(self, obj: Company) -> int:
        count = getattr(obj, "_members_count", None)
        if count is not None:
            return int(count)
        return obj.members.count()

    @admin.display(description="карточек", ordering="_clients_count")
    def clients_count(self, obj: Company) -> int:
        count = getattr(obj, "_clients_count", None)
        if count is not None:
            return int(count)
        return obj.clients.count()

    def get_queryset(self, request: HttpRequest) -> QuerySet[Company]:
        from django.db.models import Count

        return (
            super()
            .get_queryset(request)
            .annotate(
                _members_count=Count("members", distinct=True),
                _clients_count=Count("clients", distinct=True),
            )
        )


@admin.register(Call)
class CallAdmin(ModelAdmin):
    """Mango VPBX call journal — rows arrive via telephony webhook.

    Звонки без привязанного клиента видны всем менеджерам (общий
    коммутатор); привязанные проверяются скоупом при скачивании записи.
    """

    list_display = (
        "started_at",
        "direction",
        "from_number",
        "to_number",
        "extension",
        "manager",
        "client",
        "state",
        "talk_duration",
        "has_recording",
    )
    list_display_links = ("from_number", "to_number")
    list_filter = ("direction", "state", "started_at", "extension")
    search_fields = (
        "entry_id",
        "from_number",
        "to_number",
        "client__name",
        "client__email",
        "manager__email",
    )
    autocomplete_fields = ("client", "lead", "manager")

    class Media:
        """«Заявка» autocomplete фильтруется по выбранному клиенту."""

        js = (_versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),)

    readonly_fields = (
        "entry_id",
        "call_id",
        "direction",
        "state",
        "from_number",
        "to_number",
        "extension",
        "started_at",
        "connected_at",
        "finished_at",
        "talk_duration",
        "recording_id",
        "recording_link",
        "last_seq",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "started_at"
    ordering = ("-started_at", "-id")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Calls arrive via Mango webhook only."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet[Call]:
        qs = super().get_queryset(request).select_related("client", "lead", "manager")
        qs = scope_calls_for_manager(qs, request.user)
        return filter_autocomplete_by_client(request, qs)

    @admin.display(description="Запись", boolean=True)
    def has_recording(self, obj: Call) -> bool:
        """Recording file stored in private media."""
        return bool(obj.recording)

    @admin.display(description="Запись разговора")
    def recording_link(self, obj: Call) -> str:
        """Scoped download link for the stored recording."""
        if not obj.recording:
            if obj.recording_id:
                return str(_("Запись есть в Mango, ещё не скачана"))
            return "—"
        url = reverse("admin:crm_call_recording_download", args=[obj.pk])
        return format_html('<a href="{}">Скачать запись</a>', url)

    def get_urls(self) -> list[Any]:
        """Scoped staff download endpoint for call recordings."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/recording/",
                self.admin_site.admin_view(self.recording_view),
                name="crm_call_recording_download",
            ),
        ]
        return custom + urls

    def recording_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Serve the recording only if the manager sees this call's client."""
        obj = get_object_or_404(Call, pk=pk)
        if not obj.recording:
            raise PermissionDenied(_("Запись для этого звонка не сохранена."))
        if obj.client_id:
            visible = scope_clients_for_manager(
                Client.objects.filter(pk=obj.client_id),
                request.user,
            ).exists()
            if not visible:
                raise PermissionDenied(_("Нет доступа к звонку этого клиента."))
        return FileResponse(
            open(obj.recording.path, "rb"),
            as_attachment=True,
            filename=f"call-{obj.entry_id[-12:]}.mp3",
        )
