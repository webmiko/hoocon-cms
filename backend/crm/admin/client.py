"""Client card admin: timeline, compose, spec import."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, cast

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from config.unfold_callbacks import _versioned_static
from crm.admin.inlines import (
    ActivityInline,
    CallInline,
    ClientDocumentInline,
    ConversationInline,
    EmailMessageInline,
    LeadInline,
    OrderInline,
    QuoteInline,
    RmaCaseInline,
)
from crm.admin.scope import OverdueNextContactFilter
from crm.forms import ComposeEmailForm, SpecImportForm
from crm.mail_links import staff_reply_to_email
from crm.manager_signatures import manager_reply_signature
from crm.models import Activity, Client, EmailStatus, EmailTemplate
from crm.services import (
    create_outbound_email,
    email_template_context_for_client,
    get_active_email_template,
    render_email_template,
    scope_clients_for_manager,
)
from leads.models import Lead
from leads.services import lead_visible_to_manager

logger = logging.getLogger(__name__)


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
        permissions=("change",),
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
        from crm.novosystem import initiate_employee_call, novosystem_configured

        extension = ""
        uis_employee_id = ""
        profile = getattr(request.user, "vpbx_profile", None)
        if profile is not None and profile.is_enabled:
            extension = profile.extension
            uis_employee_id = (profile.uis_employee_id or "").strip()
        blockers: list[str] = []
        use_mango = mango_configured() or webhook_callback_configured()
        use_uis = novosystem_configured()
        can_mango = bool(use_mango and extension)
        can_uis = bool(use_uis and uis_employee_id)
        if not use_mango and not use_uis:
            blockers.append(str(_("Телефония выключена: включите виджет Mango или Новосистем в интеграциях.")))
        elif not can_mango and not can_uis:
            if use_mango:
                blockers.append(
                    str(_("У вас не задан добавочный — укажите его в профиле пользователя («Телефония сотрудника»)."))
                )
            if use_uis:
                blockers.append(str(_("Укажите ID сотрудника UIS в профиле пользователя («Телефония сотрудника»).")))
        if not client.phone:
            blockers.append(str(_("У клиента не заполнен телефон.")))

        if request.method == "POST" and not blockers:
            try:
                if can_mango and mango_configured():
                    result = initiate_callback(extension, client.phone)
                    via = "Mango"
                elif can_mango:
                    initiate_callback_webhook(extension, client.phone)
                    result = {}
                    via = "Mango"
                else:
                    result = {
                        "call_session_id": initiate_employee_call(
                            employee_id=uis_employee_id,
                            employee_phone="",
                            contact=client.phone,
                        )
                    }
                    via = "Новосистем"
            except RuntimeError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                self.message_user(
                    request,
                    _("Вызов инициирован: %(via)s соединит вас с %(phone)s.") % {"via": via, "phone": client.phone},
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
