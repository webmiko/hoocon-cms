"""Quote admin and its form."""

from __future__ import annotations

import json
from typing import Any, cast

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin, ScopedForeignKeyMixin, filter_autocomplete_by_client
from config.unfold_callbacks import _versioned_static
from crm.admin.inlines import QuoteItemInline
from crm.admin.scope import _CLIENT_AND_LEAD
from crm.models import Client, Quote, QuoteStatus
from crm.services import scope_quotes_for_manager
from leads.models import Lead


class QuoteAdminForm(forms.ModelForm):
    """«Заявка» КП должна принадлежать выбранному клиенту."""

    class Meta:
        model = Quote
        fields = "__all__"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        lead = self.fields.get("lead")
        if lead is not None:
            lead.help_text = (
                "Заявка, из которой выдано КП (закрывается при «Выдано»). "
                "Пока «Позиции КП» без цены и без строк, набранных вручную, "
                "артикулы этой заявки подставляются туда. Цену нужно вписать."
            )

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
class QuoteAdmin(ScopedForeignKeyMixin, OpenChangeLinkMixin, ModelAdmin):
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
    list_before_template = "admin/includes/hoocon_page_memo.html"
    change_form_template = "admin/crm/quote/change_form.html"
    # Inside the <form>: the «Выдать клиенту» button must save the edits too.
    change_form_before_template = "admin/crm/quote/issue_panel.html"
    search_fields = (
        "number",
        "client__email",
        "client__name",
        "client__company",
        "items__sku_code",
    )
    autocomplete_fields = ("client", "lead", "created_by")
    scoped_fk = _CLIENT_AND_LEAD
    readonly_fields = ("number", "sent_at", "created_at", "updated_at")
    inlines = (QuoteItemInline,)

    class Media:
        """Chained «Заявка» + канбан статусов КП."""

        js = (
            _versioned_static("admin/js/hoocon-admin-chained-autocomplete.js"),
            _versioned_static("admin/js/hoocon-admin-quotes-board.js"),
            _versioned_static("admin/js/hoocon-admin-quote-sku-code.js"),
            _versioned_static("admin/js/hoocon-admin-quote-lead-items.js"),
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Quote]:
        """Scope quotes to visible clients; autocomplete may further filter by ?client=."""
        qs = super().get_queryset(request).select_related("client", "lead", "created_by")
        qs = scope_quotes_for_manager(qs, request.user)
        return filter_autocomplete_by_client(request, qs)

    fieldsets = (
        (
            "Кому и по какой заявке",
            {
                "fields": ("client", "lead", "created_by"),
                "description": "Выберите клиента. Если КП делаете по заявке, выберите и её: позиции подставятся сами.",
            },
        ),
        (
            "Условия",
            {
                "fields": ("valid_until", "vat_rate", "comment"),
                "description": "Срок действия, НДС и условия: сроки, доставка, особые договорённости. Попадает в PDF.",
            },
        ),
        (
            "Номер и статус",
            {
                "fields": ("number", "status"),
                "classes": ("collapse",),
                "description": (
                    "Обычно статус менять не нужно: «Выдать клиенту» и кнопки «Клиент согласился / отказался» "
                    "делают это сами."
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

    def get_changeform_initial_data(self, request: HttpRequest) -> dict[str, Any]:
        """A new КП belongs to the manager who creates it unless told otherwise."""
        initial = dict(super().get_changeform_initial_data(request))
        initial.setdefault("created_by", request.user.pk)
        return initial

    def add_view(
        self,
        request: HttpRequest,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Show the three steps above a blank offer."""
        extra = dict(extra_context or {})
        extra["quote_add_hint"] = True
        return super().add_view(request, form_url, extra_context=extra)

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
        extra["hoocon_tabs"] = self._list_tabs(request)
        return super().changelist_view(request, extra_context=extra)

    def _list_tabs(self, request: HttpRequest) -> list[Any]:
        """«Черновики / Ждут ответа / Согласовано / Отклонено» above the list."""
        from django.db.models import Q

        from crm.list_tabs import TabSpec, build_list_tabs

        specs = [
            TabSpec("Все", hint="Все КП, которые вы видите"),
            TabSpec("Черновики", {"status__exact": "draft"}, Q(status=QuoteStatus.DRAFT), "Ещё не выданы клиенту"),
            TabSpec("Ждут ответа", {"status__exact": "sent"}, Q(status=QuoteStatus.SENT), "Выданы, клиент думает"),
            TabSpec(
                "Согласовано",
                {"status__exact": "accepted"},
                Q(status=QuoteStatus.ACCEPTED),
                "Клиент сказал «да»: можно создавать заказ",
            ),
            TabSpec("Отклонено", {"status__exact": "rejected"}, Q(status=QuoteStatus.REJECTED), "Клиент отказался"),
        ]
        return build_list_tabs(request.GET, self.get_queryset(request), specs)

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
        quote = self.get_object(request, object_id)
        if quote is not None:
            from crm.quote_ops import build_issue_panel

            extra_context["quote_issue"] = build_issue_panel(
                quote,
                can_change=self.has_change_permission(request, quote),
                can_order=request.user.has_perm("cabinet.add_order"),
            )
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self) -> list:
        """Kanban set-status + duplicate + order-from-quote."""
        urls = super().get_urls()
        custom = [
            path(
                "sku-code/",
                self.admin_site.admin_view(self.sku_code_view),
                name="crm_quote_sku_code",
            ),
            path(
                "lead-items/",
                self.admin_site.admin_view(self.lead_items_view),
                name="crm_quote_lead_items",
            ),
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

    def sku_code_view(self, request: HttpRequest) -> JsonResponse:
        """Article code for the readonly cell when a SKU is picked."""
        if request.method != "GET":
            return JsonResponse({"sku_code": ""}, status=405)
        if not (request.user.has_perm("crm.change_quote") or request.user.has_perm("crm.add_quote")):
            raise PermissionDenied
        raw = (request.GET.get("id") or "").strip()
        if not raw.isdigit():
            return JsonResponse({"sku_code": ""})
        from catalog.models import SKU

        code = SKU.objects.filter(pk=int(raw)).values_list("sku_code", flat=True).first()
        return JsonResponse({"sku_code": code or ""})

    def lead_items_view(self, request: HttpRequest) -> JsonResponse:
        """Articles of a visible lead, for the empty «Позиции КП» block."""
        if request.method != "GET":
            return JsonResponse({"items": []}, status=405)
        if not (request.user.has_perm("crm.change_quote") or request.user.has_perm("crm.add_quote")):
            raise PermissionDenied
        raw = (request.GET.get("id") or "").strip()
        if not raw.isdigit():
            return JsonResponse({"items": []})
        from crm.services import quote_lines_from_lead
        from leads.services import scope_leads_for_manager

        lead = scope_leads_for_manager(Lead.objects.all(), request.user).filter(pk=int(raw)).first()
        if lead is None:
            return JsonResponse({"items": []})
        return JsonResponse({"items": quote_lines_from_lead(lead)})

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
        from crm.quote_ops import transition_quote

        _, error = transition_quote(quote, status, actor=request.user)
        if error:
            return JsonResponse({"ok": False, "error": error, "status": quote.status}, status=409)
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

    def save_model(self, request: HttpRequest, obj: Quote, form: Any, change: bool) -> None:
        """«Выдать клиенту» is a draft turned into «Выдано» by one button."""
        if "_issue_quote" in request.POST and obj.status == QuoteStatus.DRAFT:
            obj.status = QuoteStatus.SENT
        super().save_model(request, obj, form, change)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        """First SENT transition stamps sent_at, issues PDF and closes the lead.

        Runs after the item inlines are saved: the PDF and the client email
        must list the positions submitted in this same form.
        """
        super().save_related(request, form, formsets, change)
        obj = cast(Quote, form.instance)
        from crm.quote_ops import finalize_quote_status, issued_message

        if "_issue_quote" in request.POST and obj.status == QuoteStatus.SENT and not obj.items.exists():
            # An empty offer must never reach a client: back to draft.
            obj.status = QuoteStatus.DRAFT
            obj.save(update_fields=["status", "updated_at"])
            self.message_user(request, "КП не выдано: добавьте хотя бы одну позицию.", messages.ERROR)
            return
        result = finalize_quote_status(obj, actor=request.user)
        if result["issued"]:
            self.message_user(request, issued_message(obj), messages.SUCCESS)
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
