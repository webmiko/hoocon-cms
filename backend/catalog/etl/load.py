"""Load normalized records into Django ORM (idempotent).

Spec: docs/data-quality-etl.md §4 — extract → normalize → load.
Idempotent via update_or_create keyed on slug/sku_code. Running twice
must not duplicate rows or crash on UNIQUE constraints.

Tilda ids (category/partuid, product uid) are NOT stored as PKs — we key on
slug/sku_code (SEO-stable). Tilda ids could be added later for reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from catalog.etl.normalize import (
    NormalizedAttribute,
    NormalizedCategory,
    NormalizedProduct,
)
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@dataclass
class LoadStats:
    """Counters for one load run (categories or one product)."""

    created: int = 0
    products_created: int = 0
    skus_created: int = 0
    attribute_values_created: int = 0


def _slugify_attr(title: str) -> str:
    """Derive a stable slug for an Attribute from its Russian title.

    Uses Django's slugify (handles transliteration via unicode). Falls back
    to a hash if slugify produces empty (rare for non-Latin titles).
    """
    from django.utils.text import slugify

    slug = slugify(title)
    if not slug:
        # Last-resort: ascii-safe fallback so Attribute.slug is never empty.
        slug = "attr-" + str(abs(hash(title)))
    return slug[:100]


@transaction.atomic
def load_categories(
    categories: list[NormalizedCategory],
) -> tuple[LoadStats, dict[int, Category]]:
    """Create/update Category rows from normalized data.

    Two-pass: first create top-level (parent=None), then subcategories so
    the parent FK can be resolved by slug.

    Args:
        categories: normalized category records.

    Returns:
        (LoadStats, map from tilda_id to Category) — the map is consumed by
        load_product to resolve a Product's category without storing tilda_id
        on the Category model.
    """
    stats = LoadStats()
    by_tilda_id: dict[int, Category] = {}

    # Pass 1: top-level categories.
    for nc in categories:
        if nc.parent_id is not None:
            continue
        _, created = Category.objects.update_or_create(
            slug=nc.slug,
            defaults={"name": nc.name, "parent": None},
        )
        by_tilda_id[nc.tilda_id] = Category.objects.get(slug=nc.slug)
        stats.created += int(created)

    # Pass 2: subcategories — resolve parent by tilda_id.
    for nc in categories:
        if nc.parent_id is None:
            continue
        parent = by_tilda_id.get(nc.parent_id)
        _, created = Category.objects.update_or_create(
            slug=nc.slug,
            defaults={"name": nc.name, "parent": parent},
        )
        by_tilda_id[nc.tilda_id] = Category.objects.get(slug=nc.slug)
        stats.created += int(created)

    # Re-link subcategories whose parent arrived in pass 1 after them.
    for nc in categories:
        if nc.parent_id is None:
            continue
        cat = by_tilda_id.get(nc.tilda_id)
        if cat is None or cat.parent is not None:
            continue
        parent = by_tilda_id.get(nc.parent_id)
        if parent is not None and parent.pk != cat.pk:
            cat.parent = parent
            cat.save(update_fields=["parent"])

    return stats, by_tilda_id


@transaction.atomic
def load_product(
    np: NormalizedProduct,
    category_map: dict[int, Category] | None = None,
) -> LoadStats:
    """Create/update one Product + its SKUs + AttributeValues.

    Args:
        np: normalized product record.
        category_map: tilda_id → Category (from load_categories). Required
            when np.category_id is set; if the id is missing from the map,
            raises QuarantineError (Product.category is NOT NULL).

    Returns:
        LoadStats with products_created / skus_created / attribute_values_created.

    Raises:
        QuarantineError: if np.category_id is set but not in category_map.
    """
    from catalog.etl.normalize import QuarantineError

    stats = LoadStats()

    category: Category | None = None
    if np.category_id is not None:
        if category_map is None or np.category_id not in category_map:
            raise QuarantineError(
                f"category not found: tilda_id={np.category_id}",
                {"uid": np.tilda_uid, "title": np.name, "category_id": np.category_id},
            )
        category = category_map[np.category_id]

    product, created = Product.objects.update_or_create(
        slug=np.slug,
        defaults={
            "name": np.name,
            "description": np.description,
            "category": category,
        },
    )
    stats.products_created += int(created)

    for nsku in np.skus:
        sku, sku_created = SKU.objects.update_or_create(
            sku_code=nsku.sku_code,
            defaults={
                "product": product,
                "name": nsku.name,
                "slug": nsku.slug,
                "price": nsku.price,
            },
        )
        stats.skus_created += int(sku_created)

        for nattr in nsku.attributes:
            attr = _ensure_attribute(nattr)
            _, av_created = AttributeValue.objects.update_or_create(
                sku=sku,
                attribute=attr,
                defaults={"value": nattr.value},
            )
            stats.attribute_values_created += int(av_created)

    return stats


def _ensure_attribute(nattr: NormalizedAttribute) -> Attribute:
    """Get or create an Attribute dictionary entry (keyed by slug)."""
    slug = _slugify_attr(nattr.title)
    attr, _ = Attribute.objects.get_or_create(
        slug=slug,
        defaults={"name": nattr.title},
    )
    # If the attribute exists but the name was updated, keep the latest name.
    if attr.name != nattr.title:
        attr.name = nattr.title
        attr.save(update_fields=["name"])
    return attr
