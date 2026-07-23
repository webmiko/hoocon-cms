"""Canonical nested catalog URL helpers (one page per SKU).

Paths::

    /catalog
    /catalog/{category_slug}
    /catalog/{category_slug}/{sku_slug}
"""

from __future__ import annotations

from typing import Any


def catalog_category_path(category_slug: str) -> str:
    """Return ``/catalog/{slug}`` or ``/catalog`` when empty."""
    slug = (category_slug or "").strip().strip("/")
    return f"/catalog/{slug}" if slug else "/catalog"


def catalog_sku_path(category_slug: str, sku_slug: str) -> str:
    """Return nested SKU path or ``/catalog`` when either segment is missing."""
    cat = (category_slug or "").strip().strip("/")
    sku = (sku_slug or "").strip().strip("/")
    if not cat or not sku:
        return "/catalog"
    return f"/catalog/{cat}/{sku}"


def catalog_path_for_sku(sku: Any) -> str:
    """Build nested path from a SKU with ``product.category`` available."""
    slug = getattr(sku, "slug", None) or ""
    product = getattr(sku, "product", None)
    category = getattr(product, "category", None) if product is not None else None
    cat_slug = getattr(category, "slug", None) or ""
    return catalog_sku_path(str(cat_slug), str(slug))
