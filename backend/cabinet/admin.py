"""Django Admin for the client cabinet: specs (read-only), orders, RMA."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpRequest
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from cabinet.models import Order, OrderItem, RmaCase, SpecList, SpecListItem
from config.admin_mixins import filter_autocomplete_by_client
from crm.models import Client
from crm.services import scope_clients_for_manager


class SpecListItemInline(TabularInline):
    """Spec positions (read-only for managers — ЛК-2, план §7)."""

    model = SpecListItem
    extra = 0
    fields = ("sku_code", "sku", "quantity", "position")
    readonly_fields = ("sku_code", "sku", "quantity", "position")
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(SpecList)
class SpecListAdmin(ModelAdmin):
    """Spec template — read-only for managers (clients own the CRUD)."""

    list_display = ("name", "account", "items_count", "updated_at")
    search_fields = ("name", "account__email")
    readonly_fields = ("account", "name", "note", "created_at", "updated_at")
    inlines = (SpecListItemInline,)

    @admin.display(description="позиций")
    def items_count(self, obj: SpecList) -> int:
        return obj.items.count()

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class OrderItemInline(TabularInline):
    """Order positions (editable; unit_price — admin-only per §12.1)."""

    model = OrderItem
    extra = 1
    fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
    autocomplete_fields = ("sku",)


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    """Client order — manual mode: менеджер ведёт статус и трек ТК."""

    list_display = ("number", "client", "status", "progress", "planned_ship_date", "created_at")
    list_filter = ("status", "carrier")
    search_fields = ("number", "client__email", "client__company", "track_number")
    list_select_related = ("client",)
    inlines = (OrderItemInline,)
    fieldsets = (
        (
            None,
            {"fields": ("client", "quote", "number", "status", "progress")},
        ),
        (
            "Отгрузка",
            {"fields": ("planned_ship_date", "carrier", "track_number")},
        ),
        (
            "Служебное",
            {"fields": ("external_id", "comment")},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> Any:
        """Autocomplete поля «Заказ» (документ) — только заказы клиента."""
        return filter_autocomplete_by_client(request, super().get_queryset(request))


@admin.register(RmaCase)
class RmaCaseAdmin(ModelAdmin):
    """Клиентские рекламации — обработка менеджером."""

    list_display = ("id", "subject", "client", "status", "serial_number", "created_at")
    list_filter = ("status",)
    search_fields = ("subject", "client__email", "serial_number")
    readonly_fields = ("client", "photo_link", "created_at", "updated_at")
    list_select_related = ("client", "order")

    @admin.display(description="фото")
    def photo_link(self, obj: RmaCase) -> str:
        """Staff download link through the scoped admin view."""
        if not obj.pk or not obj.photo:
            return "—"
        url = reverse("admin:cabinet_rmacase_photo", args=[obj.pk])
        return format_html('<a href="{}">фото</a>', url)

    def get_queryset(self, request: HttpRequest) -> Any:
        """Manager scope: only RMA of visible clients."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        visible = scope_clients_for_manager(Client.objects.all(), request.user).values("pk")
        return qs.filter(client_id__in=visible)

    def get_urls(self) -> list[Any]:
        """Scoped staff download endpoint for the defect photo."""
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/photo/",
                self.admin_site.admin_view(self.photo_view),
                name="cabinet_rmacase_photo",
            ),
        ]
        return custom + urls

    def photo_view(self, request: HttpRequest, pk: int) -> FileResponse:
        """Serve the photo only when the client is in manager scope."""
        obj = get_object_or_404(RmaCase, pk=pk)
        if not obj.photo:
            raise Http404
        visible = scope_clients_for_manager(
            Client.objects.filter(pk=obj.client_id),
            request.user,
        ).exists()
        if not request.user.is_superuser and not visible:
            raise PermissionDenied("Нет доступа к рекламации этого клиента.")
        return FileResponse(
            obj.photo.open("rb"),
            as_attachment=True,
            filename=(obj.photo.name or "photo").rsplit("/", 1)[-1],
        )
