"""DRF serializers for public catalog API.

Spec: docs/readiness-backend-ux.md §2.3; docs/security-baseline.md §3.2 —
цена только при SiteSettings.show_prices_on_site=True; иначе поле `price`
отсутствует + `price_on_request: true`.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from catalog.etl.attr_groups import attach_groups, group_attribute_rows
from catalog.etl.html_text import dedupe_description_lines
from catalog.etl.sku_variant import (
    filter_attributes_for_variant,
    filter_description_for_variant,
    filter_images_for_variant,
    parse_sku_variant,
    rewrite_series_tokens_for_variant,
)
from catalog.etl.tech_copy import (
    is_control_mode_attribute,
    normalize_manual_override_value,
)
from catalog.facets import (
    dedupe_attribute_values,
    extract_sku_lead,
    format_aux_switch_display,
    format_sku_heading_name,
    highlights_for_sku,
    normalize_area_attribute_value,
    paraphrase_sku_lead,
    strip_attribute_echo_from_text,
    strip_heading_echo_from_description,
    strip_lead_duplicate_lines,
)
from catalog.media_urls import RelativeImageField
from catalog.models import SKU, AttributeValue, Category, ProductFile, ProductImage
from catalog.newness import sku_is_new
from catalog.sku_access import (
    sku_attribute_values,
    sku_category_instructions,
    sku_category_slug_or_empty,
    sku_product_field,
    sku_section_text,
)
from sitesettings.models import SiteSettings


def _prices_visible() -> bool:
    """Return True if public API may expose SKU.price."""
    return bool(SiteSettings.load().show_prices_on_site)


def _sku_own_images(obj: SKU) -> list[ProductImage]:
    """Published images attached directly to this SKU (prefetch-aware)."""
    images = getattr(obj, "_prefetched_images", None)
    if images is None:
        images = list(
            obj.images.filter(is_published=True).order_by("sort_order", "id"),
        )
    return list(images)


def _family_gallery_images(obj: SKU) -> list[ProductImage]:
    """Published images from all published SKUs on the same Product.

    Cached on ``product._family_gallery_images`` so list/detail serializers
    do not re-query for every empty edition of the same family.
    """
    if not obj.product_id:
        return []
    product = getattr(obj, "product", None)
    if product is not None:
        cached = getattr(product, "_family_gallery_images", None)
        if cached is not None:
            return list(cached)

    images = list(
        ProductImage.objects.filter(
            is_published=True,
            sku__is_published=True,
            sku__product_id=obj.product_id,
        ).order_by("sort_order", "id"),
    )
    if product is not None:
        setattr(product, "_family_gallery_images", images)
    return images


def _sku_gallery_images(obj: SKU) -> list[ProductImage]:
    """Published gallery for this edition; fall back to family photos if empty.

    Editions often share one body photo (24/230, S/non-S). When a SKU has no
    own rows, reuse the Product family's gallery filtered for this control /
    torque so cards and PDP are not blank.
    """
    variant = parse_sku_variant(obj.sku_code)
    own = filter_images_for_variant(_sku_own_images(obj), variant)
    if own:
        return own
    return filter_images_for_variant(_family_gallery_images(obj), variant)


def _sku_kvs_value(obj: SKU) -> str:
    """Kvs for valve heading uniqueness (empty for actuators)."""
    for av in sku_attribute_values(obj):
        slug = (av.attribute.slug or "").casefold()
        name = (av.attribute.name or "").casefold()
        if slug.startswith("kvs") or name.startswith("kvs"):
            return str(av.value).strip()
    return ""


def _sku_heading(obj: SKU) -> str:
    """Unique display title for cards / H1 / breadcrumbs."""
    return format_sku_heading_name(
        obj.name,
        description=obj.description or "",
        sku_code=obj.sku_code or "",
        kvs=_sku_kvs_value(obj),
    )


def _family_list_heading(obj: SKU) -> str | None:
    """Series Product title for collapsed catalog cards, or None."""
    from catalog.family_cards import is_collapsible_family_product_slug

    if not obj.product_id:
        return None
    product = obj.product
    if product is None or not is_collapsible_family_product_slug(product.slug):
        return None
    name = (product.name or "").strip()
    return name or None


def _sku_description(obj: SKU) -> str:
    """Description scoped to this SKU edition (no foreign 24/230 blocks)."""
    text = dedupe_description_lines(obj.description or "")
    return filter_description_for_variant(text, parse_sku_variant(obj.sku_code))


def _sku_specs_text(obj: SKU) -> str:
    """Характеристики text scoped to this edition."""
    text = sku_section_text(obj, "specs_text")
    variant = parse_sku_variant(obj.sku_code)
    text = filter_description_for_variant(dedupe_description_lines(text), variant)
    return rewrite_series_tokens_for_variant(text, variant)


def _sku_analogs_text(obj: SKU) -> str:
    """Аналоги text for this edition only (control-aware Belimo lines)."""
    from catalog.etl.belimo_analogs import analogs_plain_text_for_sku

    return analogs_plain_text_for_sku(obj)


def _sku_attribute_rows(obj: SKU, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Deduped + variant-filtered ТТХ rows for API."""
    values = sku_attribute_values(obj)
    deduped = dedupe_attribute_values(values)
    rows = AttributeValueSerializer(deduped, many=True, context=context).data
    filtered = filter_attributes_for_variant(list(rows), parse_sku_variant(obj.sku_code))
    result: list[dict[str, Any]] = []
    for row in filtered:
        name = (row.get("name") or "").casefold()
        slug = (row.get("slug") or "").casefold()
        if is_control_mode_attribute(name=name, slug=slug):
            from catalog.etl.tech_copy import normalize_control_attribute_value

            row = {
                **row,
                "value": normalize_control_attribute_value(
                    str(row.get("value") or ""),
                    sku_code=obj.sku_code,
                    category_slug=sku_category_slug_or_empty(obj),
                ),
            }
        elif slug == "manual-override" or "ручн" in name:
            row = {
                **row,
                "value": normalize_manual_override_value(str(row.get("value") or "")),
            }
        if "напряж" in name and "диапазон" not in name:
            from catalog.etl.tech_copy import normalize_voltage_attribute_value

            row = {
                **row,
                "value": normalize_voltage_attribute_value(
                    str(row.get("value") or ""),
                    sku_code=obj.sku_code,
                ),
            }
        if "площад" in name:
            row = {
                **row,
                "value": normalize_area_attribute_value(str(row.get("value") or "")),
            }
        if "вспомогательн" in name:
            formatted = format_aux_switch_display(
                str(row.get("value") or ""),
                sku_code=obj.sku_code,
                description=obj.description or "",
            )
            if formatted is None:
                # Absent → omit the row (no «Нет» in ТТХ).
                continue
            row = {**row, "value": formatted}
        if "время поворота" in name or "время срабатывания" in name:
            from catalog.etl.tech_copy import (
                attribute_display_unit,
                normalize_running_time_value,
            )

            value = normalize_running_time_value(str(row.get("value") or ""))
            row = {
                **row,
                "value": value,
                "unit": attribute_display_unit(value, str(row.get("unit") or "")),
            }
        else:
            from catalog.etl.tech_copy import attribute_display_unit

            row = {
                **row,
                "unit": attribute_display_unit(
                    str(row.get("value") or ""),
                    str(row.get("unit") or ""),
                ),
            }
        result.append(row)
    return attach_groups(result)


class CategorySerializer(serializers.ModelSerializer):
    """Public category list/detail fields (series overview + install)."""

    image = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id",
            "name",
            "slug",
            "parent",
            "description",
            "instructions",
            "image",
        )
        read_only_fields = fields

    def get_image(self, obj: Category) -> dict[str, Any] | None:
        """First published product photo in this category (homepage tiles)."""
        preview_map = self.context.get("preview_images")
        if isinstance(preview_map, dict):
            img = preview_map.get(obj.pk)
            if img is None:
                return None
            return ProductImageSerializer(img, context=self.context).data
        img = (
            ProductImage.objects.filter(
                is_published=True,
                sku__is_published=True,
                sku__product__category_id=obj.pk,
            )
            .order_by("sort_order", "id")
            .first()
        )
        if img is None:
            return None
        return ProductImageSerializer(img, context=self.context).data


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


class ProductImageSerializer(serializers.ModelSerializer):
    """Public product image (full WebP + optional card preview)."""

    image = RelativeImageField(read_only=True)
    image_card = RelativeImageField(read_only=True)

    class Meta:
        model = ProductImage
        fields = ("id", "image", "image_card", "alt", "sort_order")
        read_only_fields = fields


class SKUListSerializer(serializers.ModelSerializer):
    """SKU card for list: key ТТХ highlights; price gated by SiteSettings."""

    name = serializers.SerializerMethodField()
    price_on_request = serializers.SerializerMethodField()
    in_stock = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    category_slug = serializers.CharField(
        source="product.category.slug",
        read_only=True,
    )
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    image = serializers.SerializerMethodField()
    highlights = serializers.SerializerMethodField()
    edition_count = serializers.SerializerMethodField()

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
            "in_stock",
            "is_new",
            "first_published_at",
            "edition_count",
            "image",
            "highlights",
        )
        read_only_fields = fields

    def get_name(self, obj: SKU) -> str:
        """H1/card title: series Product name on family list cards, else edition."""
        view = self.context.get("view")
        if view is not None and getattr(view, "action", None) == "list":
            family_title = _family_list_heading(obj)
            if family_title:
                return family_title
        return _sku_heading(obj)

    def get_price_on_request(self, _obj: SKU) -> bool:
        """True when prices are hidden (RFQ policy)."""
        return not _prices_visible()

    def get_in_stock(self, obj: SKU) -> bool:
        """True when warehouse quantity is positive (no raw qty in public API)."""
        return obj.in_stock

    def get_is_new(self, obj: SKU) -> bool:
        """True when first_published_at is within the Новинки window (30 days)."""
        return sku_is_new(obj)

    def get_edition_count(self, obj: SKU) -> int:
        """Published SKU count on the same Product (family card signal)."""
        annotated = getattr(obj, "edition_count", None)
        if annotated is not None:
            return max(1, int(annotated))
        if not obj.product_id:
            return 1
        count = SKU.objects.filter(
            product_id=obj.product_id,
            is_published=True,
        ).count()
        return max(1, count)

    def get_image(self, obj: SKU) -> dict[str, Any] | None:
        """Primary published image for catalog cards (sort_order ASC)."""
        images = _sku_gallery_images(obj)
        if not images:
            return None
        return ProductImageSerializer(images[0], context=self.context).data

    def get_highlights(self, obj: SKU) -> list[dict[str, str]]:
        """Compact ТТХ for catalog cards (moment / voltage / control / …)."""
        values = sku_attribute_values(obj)
        deduped = dedupe_attribute_values(values)
        variant = parse_sku_variant(obj.sku_code)
        rows = [{"name": av.attribute.name, "value": str(av.value).strip()} for av in deduped]
        allowed = {(row["name"], row["value"]) for row in filter_attributes_for_variant(rows, variant)}
        filtered = [av for av in deduped if (av.attribute.name, str(av.value).strip()) in allowed]
        return highlights_for_sku(
            filtered,
            # Room for Y/U + aux after «Управление» on modulating editions.
            limit=8,
            description=obj.description or "",
            sku_code=obj.sku_code,
            category_slug=sku_category_slug_or_empty(obj),
        )

    def to_representation(self, instance: SKU) -> dict[str, Any]:
        """Drop `price` key entirely when show_prices_on_site is False."""
        data = super().to_representation(instance)
        if not _prices_visible():
            data.pop("price", None)
        return data


class SKUDetailSerializer(SKUListSerializer):
    """SKU PDP payload: list fields + sectioned copy + attributes + files."""

    attributes = serializers.SerializerMethodField()
    attribute_groups = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    lead = serializers.SerializerMethodField()
    specs_text = serializers.SerializerMethodField()
    analogs_text = serializers.SerializerMethodField()
    category_name = serializers.CharField(
        source="product.category.name",
        read_only=True,
    )
    category_description = serializers.CharField(
        source="product.category.description",
        read_only=True,
    )
    category_instructions = serializers.SerializerMethodField()
    ball_valve_kit = serializers.SerializerMethodField()
    siblings = serializers.SerializerMethodField()
    variant_axes = serializers.SerializerMethodField()

    class Meta(SKUListSerializer.Meta):
        fields = (
            *SKUListSerializer.Meta.fields,
            "description",
            "lead",
            "specs_text",
            "analogs_text",
            "category_name",
            "category_description",
            "category_instructions",
            "ball_valve_kit",
            "siblings",
            "variant_axes",
            "attributes",
            "attribute_groups",
            "files",
            "images",
        )

    def get_description(self, obj: SKU) -> str:
        """Return description for this SKU edition only (no H1/lead/EAV echo).

        Drops bullets that only restate AttributeValue rows already shown in
        ТТХ cards / highlights (e.g. «Управление: …», «Вспомогательный…»).
        When nothing remains but a hero lead exists, return a light paraphrase
        of that lead for the Описание tab (SEO-safe, not an exact duplicate).
        """
        text = _sku_description(obj)
        heading = _sku_heading(obj)
        lead = extract_sku_lead(text or obj.description or "")
        cleaned = strip_heading_echo_from_description(
            text,
            heading=heading,
            lead=lead,
        )
        cleaned = strip_attribute_echo_from_text(
            cleaned,
            _sku_attribute_rows(obj, self.context),
        )
        cleaned = strip_lead_duplicate_lines(cleaned, lead)
        if cleaned.strip():
            return cleaned
        if lead.strip():
            return paraphrase_sku_lead(lead)
        return ""

    def get_lead(self, obj: SKU) -> str:
        """Short prose blurb for PDP hero (application sentence)."""
        return extract_sku_lead(_sku_description(obj) or obj.description or "")

    def get_specs_text(self, obj: SKU) -> str:
        """Характеристики prose — only when there are no structured attrs.

        When EAV / category cards cover the ТТХ, return empty to avoid a
        duplicate StructuredText block under the cards.
        """
        rows = _sku_attribute_rows(obj, self.context)
        if rows:
            return ""
        text = _sku_specs_text(obj)
        return strip_attribute_echo_from_text(text, rows)

    def get_highlights(self, obj: SKU) -> list[dict[str, str]]:
        """Hero ТТХ on PDP: fuller set than catalog cards."""
        values = sku_attribute_values(obj)
        deduped = dedupe_attribute_values(values)
        variant = parse_sku_variant(obj.sku_code)
        rows = [{"name": av.attribute.name, "value": str(av.value).strip()} for av in deduped]
        allowed = {(row["name"], row["value"]) for row in filter_attributes_for_variant(rows, variant)}
        filtered = [av for av in deduped if (av.attribute.name, str(av.value).strip()) in allowed]
        return highlights_for_sku(
            filtered,
            limit=11,
            description=obj.description or "",
            sku_code=obj.sku_code,
            category_slug=sku_category_slug_or_empty(obj),
        )

    def get_analogs_text(self, obj: SKU) -> str:
        """Return Аналоги for this SKU edition."""
        return _sku_analogs_text(obj)

    def get_category_instructions(self, obj: SKU) -> str:
        """Install guide scoped to this SKU edition (all series)."""
        from catalog.etl.sku_instructions import instructions_for_sku

        cat = sku_category_instructions(obj)
        stored = cat if cat.strip() else sku_product_field(obj, "instructions")
        return instructions_for_sku(obj.sku_code, stored_text=stored)

    def get_ball_valve_kit(self, obj: SKU) -> dict[str, Any] | None:
        """Optional actuator + bracket picker for ball-valve RFQ."""
        from catalog.ball_valve_kit import build_ball_valve_kit_options

        return build_ball_valve_kit_options(obj)

    def _siblings_payload(self, obj: SKU) -> list[dict[str, Any]]:
        """Memoized siblings list for this serializer instance."""
        from catalog.siblings import siblings_for_sku

        cache: dict[int, list[dict[str, Any]]] = self.context.setdefault(
            "_siblings_cache",
            {},
        )
        key = int(obj.pk or 0)
        if key in cache:
            return cache[key]
        if not obj.product_id:
            cache[key] = []
            return cache[key]
        count = SKU.objects.filter(product_id=obj.product_id, is_published=True).count()
        cache[key] = [] if count <= 1 else siblings_for_sku(obj)
        return cache[key]

    def get_siblings(self, obj: SKU) -> list[dict[str, Any]]:
        """Same-product editions for the PDP variant picker (empty if alone)."""
        return self._siblings_payload(obj)

    def get_variant_axes(self, obj: SKU) -> dict[str, list[str]]:
        """Unique DN / Kvs / voltage / control values among siblings."""
        from catalog.siblings import variant_axes_from_siblings

        rows = self._siblings_payload(obj)
        if not rows:
            return {}
        return variant_axes_from_siblings(rows)

    def get_attributes(self, obj: SKU) -> list[dict[str, Any]]:
        """ТТХ rows deduped and scoped to the SKU voltage/control variant."""
        return _sku_attribute_rows(obj, self.context)

    def get_attribute_groups(self, obj: SKU) -> list[dict[str, Any]]:
        """ТТХ grouped for category cards on the Характеристики tab."""
        return group_attribute_rows(_sku_attribute_rows(obj, self.context))

    def get_files(self, obj: SKU) -> list[dict[str, Any]]:
        """Return only published ProductFile rows, ordered."""
        qs = obj.files.filter(is_published=True).order_by("sort_order", "title")
        return ProductFileSerializer(qs, many=True, context=self.context).data

    def get_images(self, obj: SKU) -> list[dict[str, Any]]:
        """Return published gallery images for this edition only."""
        images = _sku_gallery_images(obj)
        return ProductImageSerializer(images, many=True, context=self.context).data
