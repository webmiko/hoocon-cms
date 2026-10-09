"""Client documents admin."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import FileResponse, HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from config.admin_mixins import OpenChangeLinkMixin, ScopedForeignKeyMixin
from config.unfold_callbacks import _versioned_static
from crm.admin.scope import _scoped_client_queryset, _scoped_order_queryset, _scoped_quote_queryset
from crm.models import Client, ClientDocument
from crm.services import scope_clients_for_manager


@admin.register(ClientDocument)
class ClientDocumentAdmin(ScopedForeignKeyMixin, OpenChangeLinkMixin, ModelAdmin):
    """Документы клиента: upload в карточке или здесь; private download."""

    list_display = ("title", "client", "kind", "edo_status", "created_at")
    list_filter = ("kind", "edo_status", "created_at")
    search_fields = ("title", "client__email", "client__company")
    autocomplete_fields = ("client", "quote", "order")
    scoped_fk = {
        "client": _scoped_client_queryset,
        "quote": _scoped_quote_queryset,
        "order": _scoped_order_queryset,
    }
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
        if not self.has_view_permission(request):
            raise PermissionDenied
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
