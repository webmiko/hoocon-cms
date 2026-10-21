"""Admin for global work marks and the planned-call calendar."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from config.admin_mixins import ScopedForeignKeyMixin
from crm.admin.scope import _CLIENT_AND_LEAD, ManagerUsesTheCard
from crm.models import PlannedTouch, PlannedTouchStatus, WorkLabel
from crm.services import planned_touch_owner_q, scope_planned_touches_for_manager

# Reuse the lead/quote chips. The status code is the filter key, not the CSS suffix.
_STATUS_CHIP = {
    PlannedTouchStatus.PLANNED: "draft",
    PlannedTouchStatus.IN_PROGRESS: "in_progress",
    PlannedTouchStatus.REACHED: "accepted",
    PlannedTouchStatus.NO_ANSWER: "rejected",
    PlannedTouchStatus.RESCHEDULED: "sent",
    PlannedTouchStatus.DONE: "done",
}


@admin.register(WorkLabel)
class WorkLabelAdmin(ManagerUsesTheCard, ModelAdmin):
    """Catalog of marks used on companies and leads."""

    list_display = ("name", "code", "kind", "sort", "is_active")
    list_display_links = ("name",)
    list_filter = ("kind", "is_active")
    search_fields = ("name", "code")
    ordering = ("sort", "name")

    def get_readonly_fields(self, request: HttpRequest, obj: WorkLabel | None = None) -> tuple[str, ...]:
        """The code is the filter key. A rename of the title does not change it."""
        del request
        if obj is not None:
            return ("code",)
        return ()


@admin.register(PlannedTouch)
class PlannedTouchAdmin(ManagerUsesTheCard, ScopedForeignKeyMixin, ModelAdmin):
    """Calendar of manager events. Date hierarchy is the month view."""

    list_display = (
        "starts_at",
        "title",
        "status_badge",
        "kind",
        "company",
        "assignee",
        "email_notified_at",
        "max_notified_at",
    )
    list_display_links = ("title",)
    list_filter = ("status", "kind", "assignee")
    search_fields = ("title", "note", "company__name")
    autocomplete_fields = ("company", "client", "lead", "assignee")
    scoped_fk = _CLIENT_AND_LEAD
    date_hierarchy = "starts_at"
    readonly_fields = ("dedupe_key", "email_notified_at", "max_notified_at", "created_at")
    actions = ("assign_to_me",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "status",
                    "title",
                    "kind",
                    "starts_at",
                    "company",
                    "client",
                    "lead",
                    "assignee",
                    "note",
                    "remind_before_minutes",
                ),
            },
        ),
        (
            "Служебное",
            {"fields": ("dedupe_key", "email_notified_at", "max_notified_at", "created_at")},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[PlannedTouch]:
        """Another manager's calls stay off the list and off the change form."""
        qs = super().get_queryset(request).select_related("company", "assignee")
        return scope_planned_touches_for_manager(qs, request.user)

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: PlannedTouch) -> str:
        """Colored progress chip. The column header sorts by the stored status."""
        chip = _STATUS_CHIP.get(obj.status, "draft")
        return format_html(
            '<span class="hoocon-lead-status hoocon-lead-status--{}">{}</span>',
            chip,
            obj.get_status_display(),
        )

    def get_urls(self) -> list[Any]:
        """POST «Назначить меня» from the home «Сегодня» list."""
        info = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                "<int:object_id>/assign-me/",
                self.admin_site.admin_view(self.assign_me_view),
                name=f"{info[0]}_{info[1]}_assign_me",
            ),
        ]
        return custom + super().get_urls()

    def assign_me_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        """Claim a free company call. A card that already has a manager stays theirs."""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            raise PermissionDenied
        touch = get_object_or_404(
            self.model.objects.select_related("company", "company__assignee"),
            pk=object_id,
        )
        owner = touch.company.assignee if touch.company_id and touch.company.assignee_id else touch.assignee
        if owner is not None and owner.pk != request.user.pk:
            raise PermissionDenied
        touch.assignee = request.user
        touch.save(update_fields=["assignee"])
        if touch.company_id and touch.company.assignee_id is None:
            touch.company.assignee = request.user
            touch.company.save(update_fields=["assignee"])
        messages.success(request, "Вы взяли звонок.")
        return redirect("admin:index")

    @admin.action(description="Назначить меня ответственным", permissions=["change"])
    def assign_to_me(self, request: HttpRequest, queryset: QuerySet[PlannedTouch]) -> None:
        """Claim a free call. A card that already has a manager stays theirs."""
        mine = getattr(request.user, "pk", None)
        claimable = queryset.none()
        if mine is not None:
            claimable = queryset.filter(planned_touch_owner_q(mine))
        updated = claimable.update(assignee=request.user)
        self.message_user(request, f"Назначено событий: {updated}.", messages.SUCCESS)

    def save_model(self, request: HttpRequest, obj: PlannedTouch, form: Any, change: bool) -> None:
        """Persist the row. PlannedTouch.save fills dedupe_key for this form and for inlines."""
        super().save_model(request, obj, form, change)
