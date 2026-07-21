"""Load normalized records into Django ORM (idempotent).

Spec: docs/data-quality-etl.md §4 — extract → normalize → load.
Idempotent via update_or_create keyed on slug/sku_code. Running twice
must not duplicate rows or crash on UNIQUE constraints.

Tilda ids (category/partuid, product uid) are NOT stored as PKs — we key on
slug/sku_code (SEO-stable). Tilda ids could be added later for reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
) -> tuple[LoadStats, dict[int, Category], list[dict[str, Any]]]:
    """Create/update Category rows from normalized data.

    Two-phase: top-level (parent=None), then subcategories resolved by
    ``parent_id`` → tilda map. Nested parents are applied in rounds until
    the map stops growing. A subcategory whose parent is never found is
    **not** written as a top-level orphan — it goes to quarantine.

    Args:
        categories: normalized category records.

    Returns:
        ``(LoadStats, tilda_id→Category, quarantined_rows)``. Quarantined
        rows are dicts ``{reason, payload}`` for CSV logging.
    """
    stats = LoadStats()
    by_tilda_id: dict[int, Category] = {}
    quarantined: list[dict[str, Any]] = []

    # Pass 1: top-level categories.
    for nc in categories:
        if nc.parent_id is not None:
            continue
        cat, created = Category.objects.update_or_create(
            slug=nc.slug,
            defaults={"name": nc.name, "parent": None},
        )
        by_tilda_id[nc.tilda_id] = cat
        stats.created += int(created)

    # Pass 2+: subcategories — only when parent is already in the map.
    pending = [nc for nc in categories if nc.parent_id is not None]
    progress = True
    while pending and progress:
        progress = False
        still_pending: list[NormalizedCategory] = []
        for nc in pending:
            parent = by_tilda_id.get(nc.parent_id) if nc.parent_id is not None else None
            if parent is None:
                still_pending.append(nc)
                continue
            cat, created = Category.objects.update_or_create(
                slug=nc.slug,
                defaults={"name": nc.name, "parent": parent},
            )
            by_tilda_id[nc.tilda_id] = cat
            stats.created += int(created)
            progress = True
        pending = still_pending

    for nc in pending:
        quarantined.append(
            {
                "reason": f"parent not found: tilda_id={nc.parent_id}",
                "payload": {
                    "id": nc.tilda_id,
                    "name": nc.name,
                    "slug": nc.slug,
                    "parent_id": nc.parent_id,
                },
            },
        )

    return stats, by_tilda_id, quarantined


@transaction.atomic
def load_product(
    np: NormalizedProduct,
    category_map: dict[int, Category] | None = None,
) -> LoadStats:
    """Create/update one Product + its SKUs + AttributeValues.

    Args:
        np: normalized product record.
        category_map: tilda_id → Category (from load_categories). Always
            required: Product.category is NOT NULL. Empty/missing category_id
            or an id absent from the map raises QuarantineError.

    Returns:
        LoadStats with products_created / skus_created / attribute_values_created.

    Raises:
        QuarantineError: if category cannot be resolved (None id or map miss).
    """
    from catalog.etl.normalize import QuarantineError

    stats = LoadStats()

    if np.category_id is None:
        raise QuarantineError(
            "empty category_id (Product.category is required)",
            {"uid": np.tilda_uid, "title": np.name},
        )
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
                "description": nsku.description,
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
