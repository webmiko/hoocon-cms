"""Django Admin for catalog models (Iter 1).

Spec: ПЛАН §6 Iter 1; docs/admin-vs-wagtail.md — редактор v1 = Django Admin.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from unfold.admin import ModelAdmin, TabularInline

from catalog.etl.stock_import import (
    StockImportError,
    build_stock_template_xlsx,
    import_stock_xlsx,
)
from catalog.forms import StockUploadForm
from catalog.models import (
    SKU,
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductFile,
    ProductImage,
)
from config.admin_mixins import OpenChangeLinkMixin


class InStockListFilter(admin.SimpleListFilter):
    """Filter SKUs by public availability label (qty > 0)."""

    title = "наличие"
    parameter_name = "in_stock"

    def lookups(
        self,
        request: HttpRequest,
        model_admin: admin.ModelAdmin,
    ) -> list[tuple[str, str]]:
        return [
            ("1", "Есть в наличии"),
            ("0", "Нет в наличии"),
        ]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:
        if self.value() == "1":
            return queryset.filter(stock_qty__gt=0)
        if self.value() == "0":
            return queryset.filter(stock_qty__lte=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for Category tree (slug = URL path segment)."""

    list_display = ("name", "slug", "parent", "updated_at")
    list_display_links = ("name",)
    list_filter = ("parent",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for Product lines (FK Category, PROTECT)."""

    list_display = ("name", "slug", "category", "updated_at")
    list_display_links = ("name",)
    list_filter = ("category",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    ordering = ("name",)


class AttributeValueInline(TabularInline):
    """Inline ТТХ on SKU change form."""

    model = AttributeValue
    extra = 0
    autocomplete_fields = ("attribute",)


class ProductFileInline(TabularInline):
    """Inline PDF documents on SKU change form."""

    model = ProductFile
    extra = 0
    fields = ("title", "file", "file_type", "is_published", "sort_order")


class ProductImageInline(TabularInline):
    """Inline product photos on SKU change form."""

    model = ProductImage
    extra = 0
    fields = ("image", "alt", "source_url", "sort_order", "is_published")


@admin.register(SKU)
class SKUAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for SKU — артикул, slug, цена (скрыта в публичном API)."""

    change_list_template = "admin/catalog/sku/change_list.html"
    list_display = (
        "sku_code",
        "name",
        "slug",
        "product",
        "stock_qty",
        "in_stock_label",
        "is_published",
        "price",
        "stock_updated_at",
        "updated_at",
    )
    list_display_links = ("sku_code", "name")
    list_filter = ("is_published", InStockListFilter, "product__category", "product")
    search_fields = ("sku_code", "name", "slug", "analog_belimo_code")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("product",)
    readonly_fields = ("stock_updated_at",)
    inlines = (AttributeValueInline, ProductImageInline, ProductFileInline)
    ordering = ("sku_code",)

    @admin.display(description="наличие", boolean=True)
    def in_stock_label(self, obj: SKU) -> bool:
        """Admin column: True when stock_qty > 0."""
        return obj.in_stock

    def get_urls(self) -> list:
        """Add stock upload + template download endpoints."""
        info = self.opts.app_label, self.opts.model_name
        custom = [
            path(
                "import-stock/",
                self.admin_site.admin_view(self.stock_upload_view),
                name=f"{info[0]}_{info[1]}_import_stock",
            ),
            path(
                "import-stock/template.xlsx",
                self.admin_site.admin_view(self.stock_template_view),
                name=f"{info[0]}_{info[1]}_stock_template",
            ),
        ]
        return custom + super().get_urls()

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Inject stock-upload URL into the changelist object-tools."""
        extra = dict(extra_context or {})
        if self.has_change_permission(request):
            extra["stock_upload_url"] = reverse("admin:catalog_sku_import_stock")
        return super().changelist_view(request, extra_context=extra)

    def stock_template_view(self, request: HttpRequest) -> HttpResponse:
        """Download a minimal Артикул | Остатки workbook."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        payload = build_stock_template_xlsx()
        response = HttpResponse(
            payload,
            content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        response["Content-Disposition"] = 'attachment; filename="ostatki-shablon.xlsx"'
        return response

    def stock_upload_view(self, request: HttpRequest) -> HttpResponse:
        """Staff form: upload 1C Excel and apply stock quantities."""
        if not self.has_change_permission(request):
            raise PermissionDenied
        changelist_url = reverse("admin:catalog_sku_changelist")
        template_url = reverse("admin:catalog_sku_stock_template")

        if request.method == "POST":
            form = StockUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded = form.cleaned_data["file"]
                try:
                    report = import_stock_xlsx(uploaded)
                except StockImportError as exc:
                    self.message_user(request, str(exc), messages.ERROR)
                else:
                    level = messages.SUCCESS if report.updated else messages.WARNING
                    self.message_user(request, report.summary(), level)
                    return HttpResponseRedirect(changelist_url)
        else:
            form = StockUploadForm()

        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "Загрузить остатки",
            "form": form,
            "template_url": template_url,
            "media": self.media,
        }
        return render(request, "admin/catalog/stock_upload.html", context)


@admin.register(Attribute)
class AttributeAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for Attribute dictionary (EAV)."""

    list_display = ("name", "slug", "unit", "updated_at")
    list_display_links = ("name",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(AttributeValue)
class AttributeValueAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for AttributeValue (SKU × Attribute)."""

    list_display = ("sku", "attribute", "value", "updated_at")
    list_display_links = ("value",)
    list_filter = ("attribute",)
    search_fields = ("sku__sku_code", "attribute__name", "value")
    autocomplete_fields = ("sku", "attribute")


@admin.register(ProductFile)
class ProductFileAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for ProductFile PDF (MIME/size validated on upload)."""

    list_display = (
        "title",
        "sku",
        "file_type",
        "is_published",
        "sort_order",
        "updated_at",
    )
    list_display_links = ("title",)
    list_filter = ("file_type", "is_published")
    search_fields = ("title", "sku__sku_code", "sku__name")
    autocomplete_fields = ("sku",)
    ordering = ("sort_order", "title")


@admin.register(ProductImage)
class ProductImageAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Admin for ProductImage (WebP gallery)."""

    list_display = ("sku", "alt", "sort_order", "is_published", "updated_at")
    list_display_links = ("alt",)
    list_filter = ("is_published",)
    search_fields = ("alt", "sku__sku_code", "source_url")
    autocomplete_fields = ("sku",)
    ordering = ("sku", "sort_order")
