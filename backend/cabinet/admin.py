"""Django Admin for the client cabinet: specs (read-only), orders, RMA."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from cabinet.models import Order, OrderItem, RmaCase, SpecList, SpecListItem
from config.admin_mixins import OpenChangeLinkMixin, filter_autocomplete_by_client
from crm.models import Client
from crm.services import (
    scope_clients_for_manager,
    scope_orders_for_manager,
    scope_spec_lists_for_manager,
)


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
class SpecListAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Spec template — read-only for managers (clients own the CRUD)."""

    list_display = ("name", "account", "items_count", "updated_at")
    list_display_links = ("name",)
    search_fields = ("name", "account__email")
    readonly_fields = ("account", "name", "note", "created_at", "updated_at")
    inlines = (SpecListItemInline,)
    change_form_template = "admin/cabinet/speclist/change_form.html"

    @admin.display(description="позиций", ordering="_items_count")
    def items_count(self, obj: SpecList) -> int:
        count = getattr(obj, "_items_count", None)
        if count is not None:
            return int(count)
        return obj.items.count()

    def get_queryset(self, request: HttpRequest) -> Any:
        qs = super().get_queryset(request).select_related("account").annotate(_items_count=Count("items"))
        return scope_spec_lists_for_manager(qs, request.user)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_urls(self) -> list[Any]:
        """«В КП» from a cabinet spec (managers cannot edit the spec itself)."""
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/create-quote/",
                self.admin_site.admin_view(self.create_quote_view),
                name="cabinet_speclist_create_quote",
            ),
        ]
        return custom + urls

    def create_quote_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        """POST: draft Quote from spec lines, attached to the CRM card."""
        spec = get_object_or_404(self.get_queryset(request), pk=object_id)
        list_url = reverse("admin:cabinet_speclist_change", args=[spec.pk])
        if request.method != "POST":
            return HttpResponseRedirect(list_url)
        if not request.user.has_perm("crm.add_quote"):
            raise PermissionDenied
        from crm.quote_ops import create_quote_from_spec

        quote = create_quote_from_spec(spec, author=request.user)
        if quote is None:
            self.message_user(
                request,
                "У аккаунта спецификации нет карточки клиента в CRM.",
                messages.ERROR,
            )
            return HttpResponseRedirect(list_url)
        self.message_user(
            request,
            f"Черновик {quote.number} создан из спецификации «{spec.name}».",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:crm_quote_change", args=[quote.pk]))


class OrderItemInline(TabularInline):
    """Order positions (editable; unit_price — admin-only per §12.1)."""

    model = OrderItem
    extra = 1
    fields = ("sku", "sku_code", "quantity", "unit_price", "sort_order")
    autocomplete_fields = ("sku",)


@admin.register(Order)
class OrderAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Client order — manual mode: менеджер ведёт статус и трек ТК."""

    list_display = ("number", "client", "status", "progress", "planned_ship_date", "created_at")
    list_display_links = ("number",)
    list_filter = ("status", "carrier")
    search_fields = ("number", "client__email", "client__company", "track_number")
    list_select_related = ("client", "quote")
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
        """Scope orders to visible clients; autocomplete may further filter by ?client=."""
        qs = scope_orders_for_manager(super().get_queryset(request), request.user)
        return filter_autocomplete_by_client(request, qs)


@admin.register(RmaCase)
class RmaCaseAdmin(OpenChangeLinkMixin, ModelAdmin):
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
