"""Activity admin."""

from __future__ import annotations

from typing import Any, cast

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin, ScopedForeignKeyMixin
from config.unfold_callbacks import _versioned_static
from crm.admin.scope import _CLIENT_AND_LEAD
from crm.models import Activity, Client
from crm.services import scope_activities_for_manager
from leads.models import Lead
from leads.services import lead_visible_to_manager


@admin.register(Activity)
class ActivityAdmin(ScopedForeignKeyMixin, OpenChangeLinkMixin, ModelAdmin):
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
    autocomplete_fields = ("client", "lead")
    readonly_fields = ("author", "created_at")
    scoped_fk = _CLIENT_AND_LEAD
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
