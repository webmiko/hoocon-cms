"""Canonical nested catalog URL helpers (one page per SKU).

Paths::

    /catalog
    /catalog/{category_slug}
    /catalog/{category_slug}/{sku_slug}

Builders strip accidental ``catalog/`` prefixes and nested
``{category}/{category}/…`` duplication so callers may pass either a bare
slug or a path fragment without doubling segments.
"""

from __future__ import annotations

from typing import Any


def _path_segment(value: str) -> str:
    """Normalize one path fragment: trim slashes, drop leading ``catalog/``."""
    segment = (value or "").strip().strip("/")
    while True:
        lower = segment.casefold()
        if lower == "catalog":
            return ""
        if lower.startswith("catalog/"):
            segment = segment.split("/", 1)[1].strip("/")
            continue
        break
    return segment


def catalog_category_path(category_slug: str) -> str:
    """Return ``/catalog/{slug}`` or ``/catalog`` when empty."""
    slug = _path_segment(category_slug)
    return f"/catalog/{slug}" if slug else "/catalog"


def catalog_sku_path(category_slug: str, sku_slug: str) -> str:
    """Return nested SKU path or ``/catalog`` when either segment is missing."""
    cat = _path_segment(category_slug)
    sku = _path_segment(sku_slug)
    if not cat or not sku:
        return "/catalog"
    # ``sku`` may already be ``{cat}/{sku}`` or ``{cat}/{cat}/{sku}``.
    parts = [part for part in sku.split("/") if part]
    while len(parts) >= 2 and parts[0].casefold() == cat.casefold():
        parts = parts[1:]
    sku = "/".join(parts)
    if not sku:
        return catalog_category_path(cat)
    return f"/catalog/{cat}/{sku}"


def catalog_path_for_sku(sku: Any) -> str:
    """Build nested path from a SKU with ``product.category`` available."""
    slug = getattr(sku, "slug", None) or ""
    product = getattr(sku, "product", None)
    category = getattr(product, "category", None) if product is not None else None
    cat_slug = getattr(category, "slug", None) or ""
    return catalog_sku_path(str(cat_slug), str(slug))
