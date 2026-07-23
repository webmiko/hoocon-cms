"""Фрагмент admin.py: Unfold ModelAdmin + типичные опции списка."""

from django.contrib import admin
from unfold.admin import ModelAdmin

# from catalog.models import SKU


# @admin.register(SKU)
class SKUAdmin(ModelAdmin):
    """Пример регистрации модели каталога."""

    list_display = ("sku_code", "title", "is_published", "updated_at")
    list_filter = ("is_published",)
    search_fields = ("sku_code", "title", "slug")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50
    ordering = ("-updated_at",)
