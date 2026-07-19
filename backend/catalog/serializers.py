"""DRF serializers for public catalog API.

Spec: docs/readiness-backend-ux.md §2.3; docs/security-baseline.md §3.2 —
цена только при SiteSettings.show_prices_on_site=True; иначе поле `price`
отсутствует + `price_on_request: true`.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from catalog.models import SKU, AttributeValue, Category, ProductFile
from sitesettings.models import SiteSettings


def _prices_visible() -> bool:
    """Return True if public API may expose SKU.price."""
    return bool(SiteSettings.load().show_prices_on_site)


class CategorySerializer(serializers.ModelSerializer):
    """Public category list/detail fields."""

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "parent", "description")
        read_only_fields = fields


class AttributeValueSerializer(serializers.ModelSerializer):
    """ТТХ row for SKU detail: slug of Attribute + value + unit."""

    name = serializers.CharField(source="attribute.name", read_only=True)
    slug = serializers.SlugField(source="attribute.slug", read_only=True)
    unit = serializers.CharField(source="attribute.unit", read_only=True)

    class Meta:
        model = AttributeValue
        fields = ("name", "slug", "unit", "value")
        read_only_fields = fields


class ProductFileSerializer(serializers.ModelSerializer):
    """Public PDF metadata (URL via FileField)."""

    class Meta:
        model = ProductFile
        fields = ("id", "title", "file", "file_type", "sort_order")
        read_only_fields = fields


class SKUListSerializer(serializers.ModelSerializer):
    """SKU card for list: no nested ТТХ; price gated by SiteSettings."""

    price_on_request = serializers.SerializerMethodField()
    category_slug = serializers.CharField(
        source="product.category.slug",
        read_only=True,
    )
    product_slug = serializers.CharField(source="product.slug", read_only=True)

    class Meta:
        model = SKU
        fields = (
            "id",
            "name",
            "slug",
            "sku_code",
            "analog_belimo_code",
            "category_slug",
            "product_slug",
            "price",
            "price_on_request",
        )
        read_only_fields = fields

    def get_price_on_request(self, _obj: SKU) -> bool:
        """True when prices are hidden (RFQ policy)."""
        return not _prices_visible()

    def to_representation(self, instance: SKU) -> dict[str, Any]:
        """Drop `price` key entirely when show_prices_on_site is False."""
        data = super().to_representation(instance)
        if not _prices_visible():
            data.pop("price", None)
        return data


class SKUDetailSerializer(SKUListSerializer):
    """SKU PDP payload: list fields + attributes + files."""

    attributes = AttributeValueSerializer(
        source="attribute_values",
        many=True,
        read_only=True,
    )
    files = serializers.SerializerMethodField()
    description = serializers.CharField(read_only=True)

    class Meta(SKUListSerializer.Meta):
        fields = (
            *SKUListSerializer.Meta.fields,
            "description",
            "attributes",
            "files",
        )

    def get_files(self, obj: SKU) -> list[dict[str, Any]]:
        """Return only published ProductFile rows, ordered."""
        qs = obj.files.filter(is_published=True).order_by("sort_order", "title")
        return ProductFileSerializer(qs, many=True, context=self.context).data
