"""Shared Attribute / AttributeValue / copy writers for catalog ETL.

Dedupes get_or_create + update_or_create used by specs_to_attrs and
series_copy_* enrichers (audit P3-2). Rows and texts edited in Admin
(``AttributeValue.is_manual``, ``copy_locked``) are never rewritten here.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from catalog.etl.attr_registry import CANONICAL_ATTRS, canonical_label
from catalog.models import ETL_COPY_FIELDS, SKU, Attribute, AttributeValue

# Keep in sync with AttributeValue.value max_length (DB constraint).
_value_max_length = AttributeValue._meta.get_field("value").max_length
if not isinstance(_value_max_length, int):
    raise TypeError("AttributeValue.value.max_length must be int")
_ATTR_VALUE_MAX_LEN = _value_max_length

# slug → Attribute for one enrichment run; None outside ``attribute_cache``.
_attribute_cache: ContextVar[dict[str, Attribute] | None] = ContextVar("etl_attribute_cache", default=None)


@contextmanager
def attribute_cache() -> Iterator[None]:
    """Reuse Attribute rows across SKUs within one run (one lookup per slug)."""
    if _attribute_cache.get() is not None:
        yield
        return
    token = _attribute_cache.set({})
    try:
        yield
    finally:
        _attribute_cache.reset(token)


def cached_attributes[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Run an enricher inside :func:`attribute_cache` (wrap outside ``atomic``)."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with attribute_cache():
            return func(*args, **kwargs)

    return wrapper


def clip_attribute_value(value: str) -> str:
    """Truncate to ``AttributeValue.value`` max_length (DB CharField).

    Args:
        value: Raw attribute value from ETL / enrichers.

    Returns:
        Value clipped to the model field length (currently 200).
    """
    return value[:_ATTR_VALUE_MAX_LEN]


def ensure_attribute(slug: str, name: str, unit: str = "") -> Attribute:
    """Get or create Attribute by slug with the registry name/unit.

    Registered slugs are synced to ``CANONICAL_ATTRS``; unregistered ones
    keep the label they were created with (Admin renames survive).

    Args:
        slug: stable Attribute.slug key.
        name: human-readable Attribute.name (used when slug is unregistered).
        unit: optional unit string (used when slug is unregistered).

    Returns:
        Persisted Attribute instance.
    """
    cache = _attribute_cache.get()
    if cache is not None and slug in cache:
        return cache[slug]
    name, unit = canonical_label(slug, name, unit)
    attr, _created = Attribute.objects.get_or_create(
        slug=slug,
        defaults={"name": name, "unit": unit},
    )
    if slug in CANONICAL_ATTRS and (attr.name != name or attr.unit != unit):
        attr.name = name
        attr.unit = unit
        attr.save(update_fields=["name", "unit"])
    if cache is not None:
        cache[slug] = attr
    return attr


def set_sku_attribute(
    sku: SKU,
    *,
    slug: str,
    value: str,
    name: str,
    unit: str = "",
) -> bool:
    """Upsert AttributeValue for ``sku`` under Attribute ``slug``.

    Args:
        sku: target SKU.
        slug: Attribute.slug.
        value: stored value (truncated to ``AttributeValue.value`` max_length).
        name: Attribute.name (used on create when slug is unregistered).
        unit: Attribute.unit (used on create when slug is unregistered).

    Returns:
        False when the row was edited in Admin and left untouched.
    """
    attr = ensure_attribute(slug, name, unit)
    clipped = clip_attribute_value(value)
    row = AttributeValue.objects.filter(sku=sku, attribute=attr).first()
    if row is None:
        AttributeValue.objects.create(sku=sku, attribute=attr, value=clipped)
        return True
    if row.is_manual:
        return False
    if row.value != clipped:
        row.value = clipped
        row.save(update_fields=["value", "updated_at"])
    return True


def clear_etl_attributes(sku: SKU) -> int:
    """Drop ETL-owned AttributeValue rows before a series rewrite.

    Args:
        sku: SKU about to be re-enriched.

    Returns:
        Number of deleted rows; Admin-edited rows (``is_manual``) stay.
    """
    deleted, _ = AttributeValue.objects.filter(sku=sku, is_manual=False).delete()
    return deleted


def write_copy(obj: Any, **fields: Any) -> list[str]:
    """Assign ETL fields on a Product/SKU and save only what changed.

    Text fields (``ETL_COPY_FIELDS``) are skipped when the object is
    ``copy_locked``; other fields (category, is_published, …) always apply.

    Args:
        obj: Product or SKU instance.
        **fields: field name → new value.

    Returns:
        Names of the fields actually saved.
    """
    locked = bool(getattr(obj, "copy_locked", False))
    changed: list[str] = []
    for field, value in fields.items():
        if locked and field in ETL_COPY_FIELDS:
            continue
        if getattr(obj, field) != value:
            setattr(obj, field, value)
            changed.append(field)
    if changed:
        obj.save(update_fields=changed)
    return changed
