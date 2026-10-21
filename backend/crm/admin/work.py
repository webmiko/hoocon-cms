"""Admin for global work marks and the planned-call calendar."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from unfold.admin import ModelAdmin

from crm.models import PlannedTouch, WorkLabel


@admin.register(WorkLabel)
class WorkLabelAdmin(ModelAdmin):
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
class PlannedTouchAdmin(ModelAdmin):
    """Calendar of manager events. Date hierarchy is the month view."""

    list_display = ("starts_at", "title", "kind", "company", "assignee", "email_notified_at", "max_notified_at")
    list_display_links = ("title",)
    list_filter = ("kind", "assignee")
    search_fields = ("title", "note", "company__name")
    autocomplete_fields = ("company", "client", "lead", "assignee")
    date_hierarchy = "starts_at"
    readonly_fields = ("dedupe_key", "email_notified_at", "max_notified_at", "created_at")
    actions = ("assign_to_me",)

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
        """The reminder goes to this manager an hour before the event."""
        updated = queryset.update(assignee=request.user)
        self.message_user(request, f"Назначено событий: {updated}.", messages.SUCCESS)

    def save_model(self, request: HttpRequest, obj: PlannedTouch, form: Any, change: bool) -> None:
        """A hand-made event needs a dedupe key so a later import does not copy it."""
        if not obj.dedupe_key:
            from django.utils import timezone

            from crm.outreach import touch_dedupe_key

            day = timezone.localtime(obj.starts_at).date()
            if obj.company_id:
                obj.dedupe_key = touch_dedupe_key(obj.company_id, obj.kind, day)
            else:
                owner = obj.client_id or 0
                obj.dedupe_key = f"manual:{owner}:{obj.kind}:{day.isoformat()}:{obj.starts_at:%H%M%S}"
            if PlannedTouch.objects.filter(dedupe_key=obj.dedupe_key).exists():
                obj.dedupe_key = f"{obj.dedupe_key}:{obj.starts_at:%H%M%S}"
        super().save_model(request, obj, form, change)
