"""Django Admin for catalog models (Iter 1).

Spec: ПЛАН §6 Iter 1; docs/admin-vs-wagtail.md — редактор v1 = Django Admin.
"""

from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

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

    list_display = (
        "sku_code",
        "name",
        "slug",
        "product",
        "is_published",
        "price",
        "updated_at",
    )
    list_display_links = ("sku_code", "name")
    list_filter = ("is_published", "product__category", "product")
    search_fields = ("sku_code", "name", "slug", "analog_belimo_code")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("product",)
    inlines = (AttributeValueInline, ProductImageInline, ProductFileInline)
    ordering = ("sku_code",)


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
