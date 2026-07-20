"""Admin registration for leads.Lead (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead; docs/readiness-backend-ux.md §2.2.
Staff manages leads via Django Admin: read/edit status, view PII in admin
context only (PII never exposed in public API — Slice 19).

Also exposes ``/admin/leads/lead/new-count/`` for the header sticker poll
and ``/admin/leads/lead/stats/`` for processing statistics.
Opening a lead marks it seen (sticker drops); status «Новая» stays until edited.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import admin, messages
from django.db.models import Case, IntegerField, QuerySet, When
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from leads.models import Lead
from leads.services import (
    apply_lead_manager_on_save,
    build_lead_processing_stats,
    count_new_leads,
    mark_lead_seen,
    take_lead_in_work,
)


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    """Admin for customer inquiries (RFQ / consultation / replacement).

    PII (email/phone) is visible to staff in Admin — that's the only
    place where full contact data is exposed. Public API (Slice 19)
    never returns email/phone in the response.
    """

    list_display = (
        "status_badge",
        "name",
        "lead_type",
        "company",
        "assignee",
        "processed_by",
        "created_at",
        "open_lead",
    )
    list_display_links = ("name",)
    list_filter = ("lead_type", "status", "assignee", "processed_by", "created_at")
    search_fields = ("name", "company", "email", "message", "analog_belimo_code")
    autocomplete_fields = ("sku", "client", "assignee", "processed_by")
    readonly_fields = ("created_at", "updated_at", "seen_at", "processed_at")
    ordering = ()
    actions = ("action_take_in_work", "action_mark_done")
    fieldsets = (
        (
            "Тип заявки",
            {
                "fields": ("lead_type", "status", "sku", "quantity", "analog_belimo_code"),
            },
        ),
        (
            "Менеджеры",
            {
                "fields": ("assignee", "processed_by", "processed_at"),
                "description": (
                    "«В работе у» — кто ведёт заявку сейчас. «Обработал» заполняется при статусе «Завершена»."
                ),
            },
        ),
        (
            "Контакт",
            {
                "fields": ("name", "email", "phone", "company", "client"),
            },
        ),
        (
            "Сообщение",
            {
                "fields": ("message",),
            },
        ),
        (
            "Метаданные",
            {
                "fields": ("seen_at", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Lead) -> str:
        """Colored status tag; «Новая» stands out on cards and table rows.

        Args:
            obj: Lead row.

        Returns:
            Safe HTML span with status label.
        """
        return format_html(
            '<span class="hoocon-lead-status hoocon-lead-status--{}">{}</span>',
            obj.status,
            obj.get_status_display(),
        )

    @admin.display(description="")
    def open_lead(self, obj: Lead) -> str:
        """Primary open button (easier than clicking the id column).

        Args:
            obj: Lead row.

        Returns:
            Safe HTML link styled as a button.
        """
        url = reverse("admin:leads_lead_change", args=[obj.pk])
        return format_html(
            '<a class="hoocon-admin-lead-open" href="{}">Открыть</a>',
            url,
        )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lead]:
        """Annotate status rank so new leads sort first.

        Does not call ModelAdmin.get_queryset order_by before annotate —
        ``_status_rank`` is not a model field.

        Args:
            request: current admin request.

        Returns:
            Lead queryset with ``_status_rank`` and default ordering.
        """
        qs = (
            self.model._default_manager.get_queryset()
            .select_related("client", "sku", "assignee", "processed_by")
            .annotate(
                _status_rank=Case(
                    When(status=Lead.LeadStatus.NEW, then=0),
                    When(status=Lead.LeadStatus.IN_PROGRESS, then=1),
                    default=2,
                    output_field=IntegerField(),
                ),
            )
        )
        return qs.order_by("_status_rank", "-created_at", "-pk")

    def get_ordering(self, request: HttpRequest) -> tuple[str, ...]:
        """New → in progress → done, then newest first.

        Args:
            request: current admin request.

        Returns:
            Ordering tuple consumed by the changelist (needs annotation).
        """
        return ("_status_rank", "-created_at", "-pk")

    def save_model(
        self,
        request: HttpRequest,
        obj: Lead,
        form: object,
        change: bool,
    ) -> None:
        """Auto-fill assignee / processed_by from status when empty.

        Args:
            request: admin request (actor = request.user).
            obj: Lead being saved.
            form: ModelForm instance.
            change: True when editing an existing row.
        """
        apply_lead_manager_on_save(obj, actor=request.user)
        super().save_model(request, obj, form, change)

    @admin.action(description="Взять в работу (назначить на меня)")
    def action_take_in_work(
        self,
        request: HttpRequest,
        queryset: QuerySet[Lead],
    ) -> None:
        """Assign selected leads to the current manager.

        Args:
            request: admin request.
            queryset: selected Lead rows.
        """
        count = 0
        for lead in queryset:
            take_lead_in_work(lead, request.user)
            count += 1
        self.message_user(
            request,
            f"Взято в работу: {count}",
            messages.SUCCESS,
        )

    @admin.action(description="Отметить обработанными (я завершил)")
    def action_mark_done(
        self,
        request: HttpRequest,
        queryset: QuerySet[Lead],
    ) -> None:
        """Mark selected leads done and stamp processed_by.

        Args:
            request: admin request.
            queryset: selected Lead rows.
        """
        now = timezone.now()
        count = 0
        for lead in queryset:
            lead.status = Lead.LeadStatus.DONE
            apply_lead_manager_on_save(lead, actor=request.user)
            if lead.processed_at is None:
                lead.processed_at = now
            lead.save()
            count += 1
        self.message_user(
            request,
            f"Завершено: {count}",
            messages.SUCCESS,
        )

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict | None = None,
    ) -> HttpResponse:
        """Add stats link to the leads changelist chrome.

        Args:
            request: admin request.
            extra_context: optional template context.

        Returns:
            Changelist response.
        """
        extra = dict(extra_context or {})
        extra["hoocon_leads_stats_url"] = reverse("admin:leads_lead_stats")
        return super().changelist_view(request, extra_context=extra)

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict | None = None,
    ) -> HttpResponse:
        """Mark lead seen on open so the header sticker drops.

        Args:
            request: admin request.
            object_id: lead pk when editing.
            form_url: unused passthrough.
            extra_context: unused passthrough.

        Returns:
            Changeform response from ModelAdmin.
        """
        if object_id and request.method == "GET":
            try:
                mark_lead_seen(int(object_id))
            except (TypeError, ValueError):
                pass
        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_urls(self) -> list:
        """Add sticker poll + processing stats endpoints.

        Returns:
            Custom URLs before default ModelAdmin URLs.
        """
        custom = [
            path(
                "new-count/",
                self.admin_site.admin_view(self.new_leads_count_view),
                name="leads_lead_new_count",
            ),
            path(
                "stats/",
                self.admin_site.admin_view(self.stats_view),
                name="leads_lead_stats",
            ),
        ]
        return custom + super().get_urls()

    def new_leads_count_view(self, request: HttpRequest) -> JsonResponse:
        """Return ``{"count": N}`` for staff sticker refresh.

        Args:
            request: authenticated staff request (enforced by admin_view).

        Returns:
            JSON with unread new-lead count.
        """
        return JsonResponse({"count": count_new_leads()})

    def stats_view(self, request: HttpRequest) -> HttpResponse:
        """Processing statistics for admins / managers.

        Query ``?days=7|30|0`` — period for done_in_period (0 = all time).

        Args:
            request: authenticated staff request.

        Returns:
            Rendered stats page.
        """
        raw_days = request.GET.get("days", "30")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 30
        since = None if days <= 0 else timezone.now() - timedelta(days=days)
        stats = build_lead_processing_stats(since=since)
        context = {
            **self.admin_site.each_context(request),
            "title": "Статистика заявок",
            "stats": stats,
            "days": days,
            "opts": self.model._meta,
            "changelist_url": reverse("admin:leads_lead_changelist"),
        }
        return render(request, "admin/leads/stats.html", context)
