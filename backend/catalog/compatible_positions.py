"""Cross-links for adapter ↔ brass 8100 valve PDP («Совместимые позиции»).

Computed from canon drive families + EAV ``bracket`` — no M2M table.
Scope B: adapters list drives + valves; brass valves list BR-M / BR-ML only.
"""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from django.db.models import Prefetch, Q, QuerySet

from catalog.ball_valve_kit import is_ball_valve_sku
from catalog.media_urls import to_media_path
from catalog.models import SKU, Attribute, AttributeValue, ProductImage
from catalog.sku_access import sku_attribute_values, sku_category_slug_or_empty

Role = Literal["drive", "valve", "bracket"]

ADAPTER_CODES: Final[frozenset[str]] = frozenset({"BR-M", "BR-ML"})

# Families listed on published brass 8100 «совместимый привод» (not whole DA).
BR_M_DRIVE_PREFIXES: Final[tuple[str, ...]] = (
    "DA4MU",
    "DA6MU",
    "DA8MU",
    "DA8MQU",
    "DA16MU",
    "DA16MQU",
)
BR_ML_DRIVE_PREFIXES: Final[tuple[str, ...]] = ("DA3FU", "DA5FU")

_DRIVE_LIMIT: Final[int] = 8
_VALVE_LIMIT: Final[int] = 8


def _normalize_code(code: str) -> str:
    return (code or "").casefold().replace(" ", "").replace("-", "")


def _bracket_text(sku: SKU) -> str:
    for av in sku_attribute_values(sku):
        attr = cast(Attribute, av.attribute)
        if (attr.slug or "").casefold() == "bracket":
            return str(av.value or "").strip()
    return ""


def bracket_uses_adapter(bracket: str, adapter_code: str) -> bool:
    """True when valve bracket EAV includes this adapter SKU code.

    ``BR-M`` must not match a lone ``BR-ML`` (substring trap).
    """
    text = (bracket or "").upper()
    code = (adapter_code or "").upper()
    if code == "BR-ML":
        return "BR-ML" in text
    if code == "BR-M":
        return "BR-M" in text.replace("BR-ML", "")
    return False


def _sku_card(sku: SKU, *, role: Role) -> dict[str, Any]:
    product = getattr(sku, "product", None)
    category = getattr(product, "category", None) if product is not None else None
    image_url: str | None = None
    images = getattr(sku, "_prefetched_objects_cache", {}).get("images")
    if images is None:
        images = list(
            sku.images.filter(is_published=True).order_by("sort_order", "id")[:1],
        )
    else:
        images = [img for img in images if getattr(img, "is_published", True)][:1]
    if images:
        field = images[0].image_card or images[0].image
        if field:
            image_url = to_media_path(field.url)
    return {
        "role": role,
        "name": sku.name,
        "slug": sku.slug,
        "sku_code": sku.sku_code,
        "category_slug": getattr(category, "slug", None) or sku_category_slug_or_empty(sku),
        "image": image_url,
    }


def _published_sku_qs() -> QuerySet[SKU]:
    return (
        SKU.objects.filter(is_published=True)
        .select_related("product", "product__category")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=ProductImage.objects.filter(is_published=True).order_by(
                    "sort_order",
                    "id",
                ),
            ),
        )
        .order_by("sku_code")
    )


def _pick_drives_for_prefixes(prefixes: tuple[str, ...], *, limit: int) -> list[SKU]:
    if not prefixes:
        return []
    qs = list(_published_sku_qs().filter(sku_code__istartswith="DA"))
    picked: list[SKU] = []
    used_products: set[int] = set()
    for prefix in prefixes:
        if len(picked) >= limit:
            break
        needle = _normalize_code(prefix)
        for sku in qs:
            if sku.product_id in used_products:
                continue
            code = _normalize_code(sku.sku_code)
            if not code.startswith(needle):
                continue
            used_products.add(int(sku.product_id))
            picked.append(sku)
            break
    return picked


def _pick_valves_for_adapter(adapter_code: str, *, limit: int) -> list[SKU]:
    """Published brass 8100 SKUs whose bracket lists this adapter (1 per Product)."""
    rows = (
        AttributeValue.objects.filter(
            attribute__slug="bracket",
            sku__is_published=True,
        )
        .filter(Q(sku__sku_code__istartswith="8100-bv") | Q(sku__sku_code__istartswith="8100Q-bv"))
        .select_related("sku", "sku__product", "sku__product__category")
        .prefetch_related(
            Prefetch(
                "sku__images",
                queryset=ProductImage.objects.filter(is_published=True).order_by(
                    "sort_order",
                    "id",
                ),
            ),
        )
        .order_by("sku__sku_code")
    )
    picked: list[SKU] = []
    used_products: set[int] = set()
    for av in rows:
        if len(picked) >= limit:
            break
        if not bracket_uses_adapter(str(av.value or ""), adapter_code):
            continue
        sku = cast(SKU, av.sku)
        if sku.product_id in used_products:
            continue
        if not is_ball_valve_sku(sku):
            continue
        used_products.add(int(sku.product_id or 0))
        picked.append(sku)
    return picked


def _adapters_from_bracket(bracket: str) -> list[SKU]:
    codes: list[str] = []
    if bracket_uses_adapter(bracket, "BR-M"):
        codes.append("BR-M")
    if bracket_uses_adapter(bracket, "BR-ML"):
        codes.append("BR-ML")
    if not codes:
        return []
    by_code = {s.sku_code.upper(): s for s in _published_sku_qs().filter(sku_code__in=codes)}
    return [by_code[c] for c in codes if c in by_code]


def _is_adapter_sku(sku: SKU) -> bool:
    return (sku.sku_code or "").upper() in ADAPTER_CODES


def compatible_positions_for_sku(sku: SKU) -> list[dict[str, Any]]:
    """Build compact related SKU cards for adapter or brass 8100 PDP.

    Returns:
        List of dicts with ``role``, ``name``, ``slug``, ``sku_code``,
        ``category_slug``, ``image`` — empty when not in scope B.
    """
    code = (sku.sku_code or "").upper()
    if _is_adapter_sku(sku):
        prefixes = BR_ML_DRIVE_PREFIXES if code == "BR-ML" else BR_M_DRIVE_PREFIXES
        drives = _pick_drives_for_prefixes(prefixes, limit=_DRIVE_LIMIT)
        valves = _pick_valves_for_adapter(code, limit=_VALVE_LIMIT)
        return [
            *[_sku_card(row, role="drive") for row in drives],
            *[_sku_card(row, role="valve") for row in valves],
        ]

    if not is_ball_valve_sku(sku):
        return []
    from catalog.etl.h81_kits import is_h81_kit_sku_code
    from catalog.etl.h8205_lav import is_h8205_sku_code

    if is_h81_kit_sku_code(code) or is_h8205_sku_code(sku.sku_code or ""):
        return []
    brackets = _adapters_from_bracket(_bracket_text(sku))
    return [_sku_card(row, role="bracket") for row in brackets]
