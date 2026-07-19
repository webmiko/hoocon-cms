"""Django Admin for catalog models (Iter 1).

Spec: ПЛАН §6 Iter 1; docs/admin-vs-wagtail.md — редактор v1 = Django Admin.
"""

from __future__ import annotations

from django.contrib import admin

from catalog.models import SKU, Attribute, AttributeValue, Category, Product, ProductFile


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    """Admin for Category tree (slug = URL path segment)."""

    list_display = ("name", "slug", "parent", "updated_at")
    list_filter = ("parent",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin for Product lines (FK Category, PROTECT)."""

    list_display = ("name", "slug", "category", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category",)
    ordering = ("name",)


class AttributeValueInline(admin.TabularInline):
    """Inline ТТХ on SKU change form."""

    model = AttributeValue
    extra = 0
    autocomplete_fields = ("attribute",)


class ProductFileInline(admin.TabularInline):
    """Inline PDF documents on SKU change form."""

    model = ProductFile
    extra = 0
    fields = ("title", "file", "file_type", "is_published", "sort_order")


@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    """Admin for SKU — артикул, slug, цена (скрыта в публичном API)."""

    list_display = (
        "sku_code",
        "name",
        "slug",
        "product",
        "is_published",
        "price",
        "updated_at",
    )
    list_filter = ("is_published", "product__category", "product")
    search_fields = ("sku_code", "name", "slug", "analog_belimo_code")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("product",)
    inlines = (AttributeValueInline, ProductFileInline)
    ordering = ("sku_code",)


@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    """Admin for Attribute dictionary (EAV)."""

    list_display = ("name", "slug", "unit", "updated_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


@admin.register(AttributeValue)
class AttributeValueAdmin(admin.ModelAdmin):
    """Admin for AttributeValue (SKU × Attribute)."""

    list_display = ("sku", "attribute", "value", "updated_at")
    list_filter = ("attribute",)
    search_fields = ("sku__sku_code", "attribute__name", "value")
    autocomplete_fields = ("sku", "attribute")


@admin.register(ProductFile)
class ProductFileAdmin(admin.ModelAdmin):
    """Admin for ProductFile PDF (MIME/size validated on upload)."""

    list_display = (
        "title",
        "sku",
        "file_type",
        "is_published",
        "sort_order",
        "updated_at",
    )
    list_filter = ("file_type", "is_published")
    search_fields = ("title", "sku__sku_code", "sku__name")
    autocomplete_fields = ("sku",)
    ordering = ("sort_order", "title")
