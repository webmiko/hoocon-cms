"""Call log admin."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from accounts.roles import staff_sees_all_leads
from config.admin_mixins import ScopedForeignKeyMixin, filter_autocomplete_by_client
from config.unfold_callbacks import _versioned_static
from crm.admin.scope import _CLIENT_AND_LEAD
from crm.models import Call, Client
from crm.services import scope_calls_for_manager, scope_clients_for_manager


@admin.register(Call)
class CallAdmin(ScopedForeignKeyMixin, ModelAdmin):
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
    scoped_fk = _CLIENT_AND_LEAD

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
                if (obj.entry_id or "").startswith("uis:"):
                    return str(_("Запись есть в UIS. Слушать её можно в личном кабинете Новосистем."))
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
        if not self.has_view_permission(request):
            raise PermissionDenied
        obj = get_object_or_404(Call, pk=pk)
        if not obj.recording:
            raise PermissionDenied(_("Запись для этого звонка не сохранена."))
        if obj.client_id:
            visible = scope_clients_for_manager(
                Client.objects.filter(pk=obj.client_id),
                request.user,
            ).exists()
        else:
            visible = obj.manager_id == request.user.pk or staff_sees_all_leads(request.user)
        if not visible:
            raise PermissionDenied(_("Нет доступа к звонку этого клиента."))
        return FileResponse(
            open(obj.recording.path, "rb"),
            as_attachment=True,
            filename=f"call-{obj.entry_id[-12:]}.mp3",
        )
