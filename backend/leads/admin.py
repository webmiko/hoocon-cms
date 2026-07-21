"""Admin registration for leads.Lead (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead; docs/readiness-backend-ux.md §2.2.
Staff manages leads via Django Admin: read/edit status, view PII in admin
context only (PII never exposed in public API — Slice 19).

Also exposes ``/admin/leads/lead/new-count/`` for the header sticker poll
and ``/admin/leads/lead/stats/`` for processing statistics.
Opening a lead marks it seen (sticker drops); status «Новая» stays until edited.

Change form opens in **view mode** by default; editing requires ``?edit=1``
or the «Редактировать» button.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, QuerySet, When
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin
from leads.models import Lead
from leads.services import (
    apply_lead_manager_on_save,
    build_lead_processing_stats,
    count_new_leads,
    log_manager_activity,
    mark_lead_seen,
    scope_leads_for_manager,
    take_lead_in_work,
)

_LEAD_EDIT_QUERY = "edit"


@admin.register(Lead)
class LeadAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for customer inquiries (RFQ / consultation / replacement).

    PII (email/phone) is visible to staff in Admin — that's the only
    place where full contact data is exposed. Public API (Slice 19)
    never returns email/phone in the response.

    Existing leads open read-only; enable changes via «Редактировать».
    """

    list_display = (
        "status_badge",
        "email_id",
        "name",
        "company",
        "lead_type",
        "assignee",
        "processed_by",
        "created_at",
    )
    list_display_links = ("email_id", "name")
    list_filter = (
        "lead_type",
        "status",
        "assignee",
        "processed_by",
        "company",
        ("seen_at", admin.EmptyFieldListFilter),
        "created_at",
    )
    search_fields = ("email", "name", "company", "message", "analog_belimo_code", "phone")
    autocomplete_fields = ("sku", "client", "assignee", "processed_by")
    readonly_fields = ("created_at", "updated_at", "seen_at", "processed_at")
    ordering = ()
    actions = ("action_take_in_work", "action_mark_done")
    change_form_template = "admin/leads/lead/change_form.html"
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
                "fields": ("email", "name", "phone", "company", "client"),
                "description": (
                    "Email = ID клиента в CRM. Несколько заявок с одним email попадают в одну карточку клиента."
                ),
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

    @admin.display(description="ID", ordering="email")
    def email_id(self, obj: Lead) -> str:
        """Lead contact ID (= CRM client email)."""
        return obj.email

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

    def is_lead_edit_mode(self, request: HttpRequest, obj: Lead | None) -> bool:
        """Whether the change form allows editing (new or ``?edit=1``)."""
        if obj is None:
            return True
        if request.POST.get("_lead_edit") == "1":
            return True
        return request.GET.get(_LEAD_EDIT_QUERY) == "1"

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: Lead | None = None,
    ) -> tuple[str, ...]:
        """All fields read-only in view mode; timestamps always locked."""
        if obj is not None and not self.is_lead_edit_mode(request, obj):
            names = [f.name for f in self.model._meta.fields]
            return tuple(names)
        return tuple(self.readonly_fields)

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict | None = None,
    ) -> HttpResponse:
        """Mark seen on open; view mode unless ``?edit=1``.

        Args:
            request: admin request.
            object_id: lead pk when editing.
            form_url: unused passthrough.
            extra_context: template context extras.

        Returns:
            Changeform response from ModelAdmin.
        """
        extra = dict(extra_context or {})
        obj: Lead | None = None
        if object_id:
            obj = self.get_object(request, object_id)
            if obj is not None and request.method == "GET":
                try:
                    mark_lead_seen(int(object_id))
                except (TypeError, ValueError):
                    pass
            edit_mode = self.is_lead_edit_mode(request, obj)
            extra["lead_view_mode"] = not edit_mode
            if obj is not None:
                change_url = reverse("admin:leads_lead_change", args=[obj.pk])
                if edit_mode:
                    extra["lead_view_url"] = change_url
                    # Keep edit=1 on the form action URL for POST.
                    if not form_url:
                        form_url = f"?{_LEAD_EDIT_QUERY}=1"
                else:
                    extra["lead_edit_url"] = f"{change_url}?{_LEAD_EDIT_QUERY}=1"
        else:
            extra["lead_view_mode"] = False

        # Reject POST without edit flag (view mode must not mutate).
        if (
            object_id
            and request.method == "POST"
            and request.GET.get(_LEAD_EDIT_QUERY) != "1"
            and request.POST.get("_lead_edit") != "1"
        ):
            return HttpResponseRedirect(
                reverse("admin:leads_lead_change", args=[object_id]),
            )

        return super().changeform_view(request, object_id, form_url, extra_context=extra)

    def response_change(
        self,
        request: HttpRequest,
        obj: Lead,
    ) -> HttpResponse:
        """After save, return to view mode (drop ``?edit=1``)."""
        response = super().response_change(request, obj)
        if isinstance(response, HttpResponseRedirect):
            view_url = reverse("admin:leads_lead_change", args=[obj.pk])
            if "_continue" in request.POST:
                return HttpResponseRedirect(f"{view_url}?{_LEAD_EDIT_QUERY}=1")
            if "_addanother" not in request.POST:
                return HttpResponseRedirect(view_url)
        return response

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lead]:
        """Annotate status rank; scope rows for non-superuser managers.

        Manager sees: new leads, own (assignee / processed_by), and leads on
        CRM clients they own. Superuser sees all.

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
        qs = scope_leads_for_manager(qs, request.user)
        return qs.order_by("_status_rank", "-created_at", "-pk")

    def get_ordering(self, request: HttpRequest) -> tuple[str, ...]:
        """New-first only on Lead changelist (needs ``_status_rank`` annotate).

        Other admins (e.g. EmailMessage FK widgets) call this without the
        annotation — return model fields only in that case.

        Args:
            request: current admin request.

        Returns:
            Ordering tuple safe for the current admin URL.
        """
        match = getattr(request, "resolver_match", None)
        url_name = getattr(match, "url_name", "") or ""
        if url_name.startswith("leads_lead_changelist"):
            return ("_status_rank", "-created_at", "-pk")
        return ("-created_at", "-pk")

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
        skipped = 0
        for lead in queryset:
            _lead, taken = take_lead_in_work(lead, request.user)
            if taken:
                count += 1
            else:
                skipped += 1
        if skipped:
            self.message_user(
                request,
                f"Взято в работу: {count}. Пропущено (уже у другого): {skipped}",
                messages.WARNING if count == 0 else messages.SUCCESS,
            )
        else:
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
            log_manager_activity(
                lead,
                author=request.user,
                subject=f"Завершена: {request.user.get_username()}",
                body="Статус → Завершена",
            )
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
            JSON with unread new-lead count (scoped for managers).
        """
        if not request.user.has_perm("leads.view_lead"):
            raise PermissionDenied
        return JsonResponse({"count": count_new_leads(user=request.user)})

    def stats_view(self, request: HttpRequest) -> HttpResponse:
        """Processing statistics for admins / managers.

        Query ``?days=7|30|0`` — period for done_in_period (0 = all time).
        Non-superuser managers see only their scoped lead set.

        Args:
            request: authenticated staff request.

        Returns:
            Rendered stats page.
        """
        if not request.user.has_perm("leads.view_lead"):
            raise PermissionDenied
        raw_days = request.GET.get("days", "30")
        try:
            days = int(raw_days)
        except (TypeError, ValueError):
            days = 30
        since = None if days <= 0 else timezone.now() - timedelta(days=days)
        scoped = scope_leads_for_manager(Lead.objects.all(), request.user)
        stats = build_lead_processing_stats(since=since, queryset=scoped)
        context = {
            **self.admin_site.each_context(request),
            "title": "Статистика заявок",
            "stats": stats,
            "days": days,
            "opts": self.model._meta,
            "changelist_url": reverse("admin:leads_lead_changelist"),
        }
        return render(request, "admin/leads/stats.html", context)
