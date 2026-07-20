"""Build side-by-side SKU compare matrix for public API.

Spec: docs/plan-compare-sku.md — max 4 SKU, highlights-based rows, «—» gaps.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch

from catalog.facets import EXTRA_HIGHLIGHT_DEFS, FACET_DEFS
from catalog.models import SKU, AttributeValue, ProductImage
from catalog.serializers import SKUListSerializer

COMPARE_MAX_SKUS = 4
COMPARE_EMPTY_CELL = "—"

# Meta rows always first (not from EAV highlights).
_META_ROW_DEFS: tuple[tuple[str, str], ...] = (
    ("sku_code", "Артикул"),
    ("analog_belimo_code", "Аналог Belimo"),
)


def parse_compare_slugs(raw: str) -> list[str]:
    """Split ``?skus=`` into ordered unique slugs.

    Args:
        raw: Comma-separated slug list from the query string.

    Returns:
        Deduped slugs preserving first-seen order (empty tokens dropped).
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for part in raw.split(","):
        slug = part.strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        ordered.append(slug)
    return ordered


def compare_row_key_order() -> list[str]:
    """Canonical highlight key order (signals after control)."""
    ordered: list[str] = []
    seen: set[str] = set()
    for facet in (*FACET_DEFS, *EXTRA_HIGHLIGHT_DEFS):
        if facet.key in {"control_signal", "feedback_signal"}:
            continue
        if facet.key not in seen:
            ordered.append(facet.key)
            seen.add(facet.key)
        if facet.key == "control":
            for signal_key in ("control_signal", "feedback_signal"):
                if signal_key not in seen:
                    ordered.append(signal_key)
                    seen.add(signal_key)
    return ordered


def normalize_compare_cell(value: str) -> str:
    """Collapse whitespace and case for diff equality."""
    return " ".join(value.casefold().split())


def format_highlight_cell(row: dict[str, str]) -> str:
    """Join highlight value + unit the same way catalog cards do."""
    value = (row.get("value") or "").strip()
    unit = (row.get("unit") or "").strip()
    if not value:
        return COMPARE_EMPTY_CELL
    if unit and unit not in value:
        return f"{value} {unit}"
    return value


def build_compare_rows(
    sku_payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build matrix rows from serialized SKU list payloads.

    Args:
        sku_payloads: ``SKUListSerializer`` dicts in column order.

    Returns:
        Rows with ``key``, ``name``, ``values``, ``diff``.
    """
    rows: list[dict[str, Any]] = []

    for meta_key, meta_name in _META_ROW_DEFS:
        values = [(str(sku.get(meta_key) or "").strip() or COMPARE_EMPTY_CELL) for sku in sku_payloads]
        rows.append(
            {
                "key": meta_key,
                "name": meta_name,
                "values": values,
                "diff": _values_differ(values),
            },
        )

    # Per-SKU highlight map: key → {name, cell}.
    maps: list[dict[str, dict[str, str]]] = []
    names: dict[str, str] = {}
    for sku in sku_payloads:
        by_key: dict[str, dict[str, str]] = {}
        for h in sku.get("highlights") or []:
            key = str(h.get("key") or "").strip()
            if not key:
                continue
            cell = format_highlight_cell(h)
            by_key[key] = {"name": str(h.get("name") or key), "cell": cell}
            names.setdefault(key, str(h.get("name") or key))
        maps.append(by_key)

    present_keys = {key for m in maps for key in m}
    for key in compare_row_key_order():
        if key not in present_keys:
            continue
        values = [m.get(key, {}).get("cell", COMPARE_EMPTY_CELL) for m in maps]
        rows.append(
            {
                "key": key,
                "name": names.get(key, key),
                "values": values,
                "diff": _values_differ(values),
            },
        )

    # Any highlight keys not in the canonical facet order (rare).
    for key in sorted(present_keys):
        if any(r["key"] == key for r in rows):
            continue
        values = [m.get(key, {}).get("cell", COMPARE_EMPTY_CELL) for m in maps]
        rows.append(
            {
                "key": key,
                "name": names.get(key, key),
                "values": values,
                "diff": _values_differ(values),
            },
        )

    return rows


def _values_differ(values: list[str]) -> bool:
    """True when normalized cells are not all equal."""
    if len(values) < 2:
        return False
    norms = {normalize_compare_cell(v) for v in values}
    return len(norms) > 1


def build_compare_response(
    skus: list[SKU],
    *,
    serializer_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize SKUs and attach compare matrix rows.

    Args:
        skus: Published SKUs in requested column order.
        serializer_context: DRF serializer context (request for media URLs).

    Returns:
        ``{"skus": [...], "rows": [...]}``.
    """
    context = serializer_context or {}
    payloads = SKUListSerializer(skus, many=True, context=context).data
    # DRF may return ReturnList — coerce to plain list of dicts.
    sku_list = [dict(item) for item in payloads]
    return {
        "skus": sku_list,
        "rows": build_compare_rows(sku_list),
    }


def resolve_compare_skus(slugs: list[str]) -> tuple[list[SKU], list[str]]:
    """Load published SKUs in slug order.

    Args:
        slugs: Requested slugs (already deduped).

    Returns:
        ``(skus_in_order, missing_slugs)``.
    """
    if not slugs:
        return [], []
    published_images = Prefetch(
        "images",
        queryset=ProductImage.objects.filter(is_published=True).order_by(
            "sort_order",
            "id",
        ),
        to_attr="_prefetched_images",
    )
    published_attrs = Prefetch(
        "attribute_values",
        queryset=AttributeValue.objects.select_related("attribute"),
        to_attr="_prefetched_attribute_values",
    )
    found = {
        sku.slug: sku
        for sku in SKU.objects.filter(is_published=True, slug__in=slugs)
        .select_related("product", "product__category")
        .prefetch_related(published_images, published_attrs)
    }
    ordered = [found[s] for s in slugs if s in found]
    missing = [s for s in slugs if s not in found]
    return cast(list[SKU], ordered), missing
