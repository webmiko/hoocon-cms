"""Tabular inlines on the CRM client card."""

from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin
from django.db.models import F, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import TabularInline

from cabinet.models import Order, RmaCase
from crm.admin.inline_extra import OneBlankInlineRowMixin
from crm.admin.scope import _scoped_lead_queryset
from crm.models import Activity, Call, ClientDocument, EmailMessage, Quote, QuoteItem
from leads.models import Lead
from leads.services import scope_leads_for_manager
from supportchat.models import Conversation


class OrderCardInlineForm(forms.ModelForm):
    """One order row on the client card. An empty number is filled on save."""

    number = forms.CharField(
        label="номер",
        required=False,
        max_length=60,
        widget=forms.TextInput(attrs={"placeholder": "Пусто — номер поставим сами"}),
    )

    class Meta:
        model = Order
        fields = ("number", "status", "comment")
        widgets = {
            "comment": forms.TextInput(attrs={"placeholder": "Звонок: что заказать"}),
        }


class OrderInline(OneBlankInlineRowMixin, TabularInline):
    """Orders on the client card (cabinet.Order)."""

    tab = True
    model = Order
    form = OrderCardInlineForm
    fields = ("number", "status", "comment", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "заказ"
    verbose_name_plural = "заказы клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Manual order from a phone call, same button as a document row."""
        if obj is None or not getattr(obj, "pk", None):
            return False
        return request.user.has_perm("cabinet.add_order")


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


class LeadCardInlineForm(forms.ModelForm):
    """One lead row. Name and email are copied from the card on save."""

    class Meta:
        model = Lead
        fields = ("lead_type", "message", "status", "assignee")
        widgets = {
            "message": forms.TextInput(attrs={"placeholder": "Что сказал клиент"}),
        }


class LeadInline(OneBlankInlineRowMixin, TabularInline):
    """RFQ / consult requests on this client card (scoped for managers)."""

    tab = True
    model = Lead
    form = LeadCardInlineForm
    fields = ("lead_type", "message", "status", "assignee", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "лид"
    verbose_name_plural = "лиды клиента"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Manual lead from the card, for a call that is not a site form."""
        if obj is None or not getattr(obj, "pk", None):
            return False
        return request.user.has_perm("leads.add_lead")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lead]:
        """Hide foreign leads that the manager cannot open in Lead Admin."""
        return scope_leads_for_manager(super().get_queryset(request), request.user)


class ActivityInline(OneBlankInlineRowMixin, TabularInline):
    """Timeline notes on a Client card."""

    tab = True
    model = Activity
    fields = ("activity_type", "subject", "body", "lead", "author", "created_at")
    readonly_fields = ("author", "created_at")
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


class QuoteItemInlineForm(forms.ModelForm):
    """The article code is a snapshot of the chosen SKU, not a second input."""

    class Meta:
        model = QuoteItem
        fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
        widgets = {
            "sku_code": forms.TextInput(
                attrs={
                    "readonly": "readonly",
                    "tabindex": "-1",
                    "placeholder": "Подставится из артикула",
                },
            ),
        }

    def clean(self) -> dict[str, Any]:
        """Keep the stored code equal to the selected SKU, ignoring typed text."""
        cleaned = super().clean() or {}
        sku = cleaned.get("sku")
        if sku is not None:
            cleaned["sku_code"] = sku.sku_code
        return cleaned


class QuoteItemInline(OneBlankInlineRowMixin, TabularInline):
    """SKU lines of a quote (manager-editable)."""

    model = QuoteItem
    form = QuoteItemInlineForm
    fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
    autocomplete_fields = ("sku",)


class QuoteCardInlineForm(forms.ModelForm):
    """Draft quote row. Product lines are chosen on the quote card itself."""

    class Meta:
        model = Quote
        fields = ("comment", "vat_rate")
        widgets = {
            "comment": forms.TextInput(
                attrs={"placeholder": "Что посчитать. Артикулы выбираются внутри этого КП"},
            ),
        }


class QuoteInline(OneBlankInlineRowMixin, TabularInline):
    """Quotes on the client card. Lines with a chosen SKU live on the quote."""

    tab = True
    model = Quote
    form = QuoteCardInlineForm
    fields = ("comment", "vat_rate", "number", "status", "created_at")
    readonly_fields = ("number", "status", "created_at")
    show_change_link = True
    can_delete = False
    ordering = ("-created_at",)
    verbose_name = "коммерческое предложение"
    verbose_name_plural = "коммерческие предложения"

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Draft КП from the card; the manager picks SKUs after opening it."""
        if obj is None or not getattr(obj, "pk", None):
            return False
        return request.user.has_perm("crm.add_quote")


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


class ClientDocumentInline(OneBlankInlineRowMixin, TabularInline):
    """Документы карточки (ЛК-3/14): КП-счёта-УПД, private download."""

    tab = True
    model = ClientDocument
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
