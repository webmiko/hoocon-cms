"""Safe accessors for SKU → Product → Category chains.

Use these instead of bare ``sku.product.category.*`` so missing FKs
(data corruption, incomplete migrations, race) do not raise AttributeError
or ``RelatedObjectDoesNotExist``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.core.exceptions import ObjectDoesNotExist

if TYPE_CHECKING:
    from catalog.models import SKU, Category, Product


def sku_product(sku: SKU | None) -> Product | None:
    """Return the related Product, or None if the FK chain is broken.

    Args:
        sku: Catalog SKU or None.

    Returns:
        Product instance, or None when ``product_id`` is empty, the row is
        missing (stale FK), or the descriptor resolves to None.
    """
    if sku is None or not sku.product_id:
        return None
    try:
        product = sku.product
    except ObjectDoesNotExist:
        return None
    return cast("Product", product)


def sku_category(sku: SKU | None) -> Category | None:
    """Return the SKU's product category, or None if any link is broken.

    Args:
        sku: Catalog SKU or None.

    Returns:
        Category instance, or None when product/category is missing.
    """
    product = sku_product(sku)
    if product is None or not product.category_id:
        return None
    try:
        category = product.category
    except ObjectDoesNotExist:
        return None
    return cast("Category", category)


def sku_category_slug(sku: SKU | None) -> str | None:
    """Return product category slug when SKU → Product → Category are set.

    Args:
        sku: Catalog SKU or None.

    Returns:
        Category slug, or None when any link in the chain is missing.
    """
    category = sku_category(sku)
    if category is None:
        return None
    return category.slug


def sku_category_slug_or_empty(sku: SKU | None) -> str:
    """Like :func:`sku_category_slug`, but ``""`` when the chain is incomplete."""
    return sku_category_slug(sku) or ""


def sku_category_instructions(sku: SKU | None) -> str:
    """Category install guide, or empty when product/category is missing.

    Args:
        sku: Catalog SKU or None.

    Returns:
        ``category.instructions`` text, or ``""``.
    """
    category = sku_category(sku)
    if category is None:
        return ""
    return category.instructions or ""


def sku_product_field(sku: SKU | None, field: str, default: str = "") -> str:
    """Read a string field from ``sku.product`` safely.

    Args:
        sku: Catalog SKU or None.
        field: Product attribute name (e.g. ``analogs_text``, ``instructions``).
        default: Value when product is missing or the field is empty.

    Returns:
        Field value or ``default``.
    """
    product = sku_product(sku)
    if product is None:
        return default
    return getattr(product, field, None) or default


def sku_section_text(sku: SKU | None, field: str) -> str:
    """Prefer SKU section text; fall back to product only when SKU value is None.

    Empty string is a deliberate SKU-level value (e.g. edition filter left no
    analogs) and must not re-inherit the product block or trigger a product
    FK fetch. Use product inherit only when the attribute is unset (``None``).

    Args:
        sku: Catalog SKU or None.
        field: Shared section name (``analogs_text``, ``specs_text``, …).

    Returns:
        SKU field when not None; otherwise ``sku_product_field`` (may be ``""``).
    """
    if sku is None:
        return ""
    value = getattr(sku, field, None)
    if value is not None:
        return value if isinstance(value, str) else str(value)
    return sku_product_field(sku, field)
