"""Shared Attribute / AttributeValue writers for catalog ETL.

Dedupes get_or_create + update_or_create used by specs_to_attrs and
series_copy_* enrichers (audit P3-2).
"""

from __future__ import annotations

from catalog.models import SKU, Attribute, AttributeValue

# Keep in sync with AttributeValue.value max_length (DB constraint).
_value_max_length = AttributeValue._meta.get_field("value").max_length
if not isinstance(_value_max_length, int):
    raise TypeError("AttributeValue.value.max_length must be int")
_ATTR_VALUE_MAX_LEN = _value_max_length


def ensure_attribute(slug: str, name: str, unit: str = "") -> Attribute:
    """Get or create Attribute by slug; sync name/unit when they drift.

    Args:
        slug: stable Attribute.slug key.
        name: human-readable Attribute.name.
        unit: optional unit string (may be empty).

    Returns:
        Persisted Attribute instance.
    """
    attr, _created = Attribute.objects.get_or_create(
        slug=slug,
        defaults={"name": name, "unit": unit},
    )
    if attr.name != name or attr.unit != unit:
        attr.name = name
        attr.unit = unit
        attr.save(update_fields=["name", "unit"])
    return attr


def set_sku_attribute(
    sku: SKU,
    *,
    slug: str,
    value: str,
    name: str,
    unit: str = "",
) -> None:
    """Upsert AttributeValue for ``sku`` under Attribute ``slug``.

    Args:
        sku: target SKU.
        slug: Attribute.slug.
        value: stored value (truncated to ``AttributeValue.value`` max_length).
        name: Attribute.name (used on create / sync).
        unit: Attribute.unit (used on create / sync).
    """
    attr = ensure_attribute(slug, name, unit)
    AttributeValue.objects.update_or_create(
        sku=sku,
        attribute=attr,
        defaults={"value": value[:_ATTR_VALUE_MAX_LEN]},
    )
