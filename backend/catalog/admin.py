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
    ADMIN_EDIT_FLAG,
    ETL_COPY_FIELDS,
    SKU,
    AnalogMap,
    Attribute,
    AttributeValue,
    Category,
    Product,
    ProductFile,
    ProductImage,
)
from config.admin_mixins import OpenChangeLinkMixin


def mark_admin_edit(obj: Any, changed: list[str], *, change: bool = True) -> None:
    """Let an Admin save through the ETL locks and set them on manual edits.

    Product/SKU: editing name or texts sets ``copy_locked``. AttributeValue:
    any edit sets ``is_manual``. ProductImage: unpublishing by hand sets
    ``hidden_by_editor``, publishing clears it. An explicit checkbox change wins.
    """
    obj.__dict__[ADMIN_EDIT_FLAG] = True
    if isinstance(obj, AttributeValue):
        if "is_manual" not in changed:
            obj.is_manual = True
    elif isinstance(obj, ProductImage):
        if "is_published" in changed:
            obj.hidden_by_editor = not obj.is_published
    elif (
        isinstance(obj, (Product, SKU))
        and change
        and "copy_locked" not in changed
        and set(changed) & set(ETL_COPY_FIELDS)
    ):
        obj.copy_locked = True


class AdminEditLockMixin:
    """Route Admin saves of the model and its inlines through ``mark_admin_edit``."""

    def save_model(self, request: HttpRequest, obj: Any, form: Any, change: bool) -> None:
        mark_admin_edit(obj, list(form.changed_data), change=change)
        super().save_model(request, obj, form, change)  # type: ignore[misc]

    def save_formset(self, request: HttpRequest, form: Any, formset: Any, change: bool) -> None:
        deleted = set(getattr(formset, "deleted_forms", ()))
        for inline_form in formset.forms:
            if inline_form in deleted or not inline_form.has_changed():
                continue
            mark_admin_edit(inline_form.instance, list(inline_form.changed_data))
        super().save_formset(request, form, formset, change)  # type: ignore[misc]


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

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("parent")


@admin.register(Product)
class ProductAdmin(AdminEditLockMixin, OpenChangeLinkMixin, ModelAdmin):
    """Admin for Product lines (FK Category, PROTECT)."""

    list_display = ("name", "slug", "category", "updated_at")
    list_display_links = ("name",)
    list_filter = ("category",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    ordering = ("name",)

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("category")

    fieldsets = (
        (
            None,
            {
                "fields": ("name", "slug", "category"),
                "description": (
                    "Канон сборки карточек серий (артикул, адрес страницы, "
                    "одна плитка на линейку, выбор издания, заявка) — документ "
                    "«Шаблоны карточек по сериям» в репозитории. Семейные "
                    "линейки: латунные краны, комплекты, воздушные без пружины, "
                    "дымоудаление и противопожарные."
                ),
            },
        ),
        (
            "Тексты линейки",
            {
                "fields": (
                    "description",
                    "instructions",
                    "specs_text",
                    "analogs_text",
                    "copy_locked",
                ),
                "classes": ("collapse",),
            },
        ),
    )


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
    fields = (
        "image",
        "image_card",
        "alt",
        "source_url",
        "sort_order",
        "is_published",
        "hidden_by_editor",
    )
    readonly_fields = ("image_card", "hidden_by_editor")


@admin.register(SKU)
class SKUAdmin(AdminEditLockMixin, OpenChangeLinkMixin, ModelAdmin):
    """Admin for SKU — артикул, slug, цена (скрыта в публичном API)."""

    change_list_template = "admin/catalog/sku/change_list.html"
    list_display = (
        "sku_code",
        "name",
        "slug",
        "product",
        "stock_qty",
        "stock_qty_ma",
        "in_stock_label",
        "in_stock_ma_label",
        "is_published",
        "first_published_at",
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

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("product")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "product",
                    "sku_code",
                    "name",
                    "slug",
                    "is_published",
                    "first_published_at",
                    "analog_belimo_code",
                ),
                "description": (
                    "Формат артикула и адрес страницы — по шаблону серии "
                    "линейки (документ «Шаблоны карточек по сериям»). "
                    "Издания одной семейной линейки должны быть привязаны "
                    "к одной карточке линейки."
                ),
            },
        ),
        (
            "Склад и цена",
            {
                "fields": (
                    "stock_qty",
                    "stock_qty_ma",
                    "stock_updated_at",
                    "price",
                ),
                "description": (
                    "Выгрузка 1С: обычная строка артикула → «остаток»; "
                    "строка артикула с пометкой 4–20 мА → «остаток 4–20 мА» "
                    "(спецзаказ). На сайте только «есть / нет»."
                ),
            },
        ),
        (
            "Тексты издания",
            {
                "fields": ("description", "specs_text", "analogs_text", "copy_locked"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="наличие", boolean=True)
    def in_stock_label(self, obj: SKU) -> bool:
        """Admin column: True when stock_qty > 0."""
        return obj.in_stock

    @admin.display(description="4–20 мА", boolean=True)
    def in_stock_ma_label(self, obj: SKU) -> bool:
        """Admin column: True when 4–20 mA special-order units are on hand."""
        return obj.in_stock_ma

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
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
            "changelist_url": changelist_url,
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
class AttributeValueAdmin(AdminEditLockMixin, OpenChangeLinkMixin, ModelAdmin):
    """Admin for AttributeValue (SKU × Attribute)."""

    list_display = ("sku", "attribute", "value", "is_manual", "updated_at")
    list_display_links = ("value",)
    list_filter = ("is_manual", "attribute")
    search_fields = ("sku__sku_code", "attribute__name", "value")
    autocomplete_fields = ("sku", "attribute")

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("sku", "attribute")


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

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("sku")


@admin.register(ProductImage)
class ProductImageAdmin(AdminEditLockMixin, OpenChangeLinkMixin, ModelAdmin):
    """Admin for ProductImage (WebP gallery)."""

    list_display = ("sku", "alt", "sort_order", "is_published", "hidden_by_editor", "updated_at")
    list_display_links = ("sku",)
    list_filter = ("is_published", "hidden_by_editor")
    readonly_fields = ("hidden_by_editor",)
    search_fields = ("alt", "sku__sku_code", "source_url")
    autocomplete_fields = ("sku",)
    ordering = ("sku", "sort_order")

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("sku")


@admin.register(AnalogMap)
class AnalogMapAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Карта аналогов (ЛК-10): сторонний артикул → Hoocon SKU + параметры."""

    list_display = ("brand", "foreign_code", "sku", "torque_nm", "spring_return", "is_active")
    list_display_links = ("brand", "foreign_code")
    list_filter = ("brand", "spring_return", "is_active")
    search_fields = ("brand", "foreign_code", "sku__sku_code", "note")
    autocomplete_fields = ("sku",)
    readonly_fields = ("foreign_code_key", "created_at", "updated_at")
    list_select_related = ("sku",)
