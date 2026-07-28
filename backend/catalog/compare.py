"""Build side-by-side SKU compare matrix for public API.

Spec: docs/plan-compare-sku.md — max 4 SKU, highlights + full ТТХ groups, «—» gaps.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch

from catalog.etl.attr_groups import (
    ATTR_GROUP_LABELS,
    ATTR_GROUP_ORDER,
    CONTROL_SIGNAL_SLUGS,
    FEEDBACK_SIGNAL_SLUGS,
    group_key_for_slug,
)
from catalog.facets import EXTRA_HIGHLIGHT_DEFS, FACET_DEFS
from catalog.models import SKU, AttributeValue, ProductImage
from catalog.serializers import SKUListSerializer, _sku_attribute_rows

COMPARE_MAX_SKUS = 4
COMPARE_EMPTY_CELL = "—"
COMPARE_META_GROUP = "meta"
COMPARE_META_GROUP_TITLE = "Основные"

# Highlight keys already covered as core rows — skip EAV aliases in «Все характеристики».
_SIGNAL_CORE_SKIP_SLUGS = CONTROL_SIGNAL_SLUGS | FEEDBACK_SIGNAL_SLUGS

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


def format_attribute_cell(row: dict[str, Any]) -> str:
    """Format an EAV attribute row for a compare cell."""
    value = str(row.get("value") or "").strip()
    unit = str(row.get("unit") or "").strip()
    if not value:
        return COMPARE_EMPTY_CELL
    if unit and unit not in value:
        return f"{value} {unit}"
    return value


def _group_meta_for_key(key: str) -> tuple[str, str]:
    """Resolve group key/title for a highlight or attribute slug."""
    if key in {meta_key for meta_key, _ in _META_ROW_DEFS}:
        return COMPARE_META_GROUP, COMPARE_META_GROUP_TITLE
    group = group_key_for_slug(key.replace("_", "-")) or group_key_for_slug(key)
    if not group:
        # Facet keys use underscores (control_signal); try dashed form.
        dashed = key.replace("_", "-")
        group = group_key_for_slug(dashed)
    if group:
        return group, ATTR_GROUP_LABELS.get(group, group)
    return "other", "Прочие"


def build_compare_rows(
    sku_payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build core matrix rows from serialized SKU list payloads.

    Args:
        sku_payloads: ``SKUListSerializer`` dicts in column order.

    Returns:
        Rows with ``key``, ``name``, ``group``, ``group_title``, ``values``,
        ``diff``, ``core`` (True — shown without «Все характеристики»).
    """
    rows: list[dict[str, Any]] = []

    for meta_key, meta_name in _META_ROW_DEFS:
        values = [(str(sku.get(meta_key) or "").strip() or COMPARE_EMPTY_CELL) for sku in sku_payloads]
        group, group_title = _group_meta_for_key(meta_key)
        rows.append(
            {
                "key": meta_key,
                "name": meta_name,
                "group": group,
                "group_title": group_title,
                "values": values,
                "diff": _values_differ(values),
                "core": True,
            },
        )

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
        group, group_title = _group_meta_for_key(key)
        rows.append(
            {
                "key": key,
                "name": names.get(key, key),
                "group": group,
                "group_title": group_title,
                "values": values,
                "diff": _values_differ(values),
                "core": True,
            },
        )

    for key in sorted(present_keys):
        if any(r["key"] == key for r in rows):
            continue
        values = [m.get(key, {}).get("cell", COMPARE_EMPTY_CELL) for m in maps]
        group, group_title = _group_meta_for_key(key)
        rows.append(
            {
                "key": key,
                "name": names.get(key, key),
                "group": group,
                "group_title": group_title,
                "values": values,
                "diff": _values_differ(values),
                "core": True,
            },
        )

    return rows


def build_attribute_compare_rows(
    skus: list[SKU],
    *,
    serializer_context: dict[str, Any] | None = None,
    core_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build full ТТХ rows from attribute_groups (non-core extras).

    Args:
        skus: Published SKUs in column order.
        serializer_context: DRF context for serializers.
        core_keys: Highlight/meta keys already in ``rows`` (skipped here).

    Returns:
        Attribute rows with ``core=False`` and group metadata.
    """
    context = serializer_context or {}
    skip = core_keys or set()
    per_sku: list[dict[str, dict[str, Any]]] = []
    names: dict[str, str] = {}
    groups: dict[str, tuple[str, str]] = {}

    for sku in skus:
        by_key: dict[str, dict[str, Any]] = {}
        for row in _sku_attribute_rows(sku, context):
            slug = str(row.get("slug") or "").strip()
            if not slug:
                continue
            # Align highlight facet keys (moment) with attr slugs (moment).
            key = slug.replace("-", "_") if "_" not in slug else slug
            # Prefer raw slug as stable key when not in facet underscore form.
            if key in skip or slug in skip:
                continue
            # Prefer slug for uniqueness across groups.
            row_key = slug
            if row_key in skip:
                continue
            cell = format_attribute_cell(row)
            by_key[row_key] = {"name": str(row.get("name") or row_key), "cell": cell}
            names.setdefault(row_key, str(row.get("name") or row_key))
            group = str(row.get("group") or "") or group_key_for_slug(slug) or "other"
            group_title = str(row.get("group_label") or "") or ATTR_GROUP_LABELS.get(
                group,
                "Прочие",
            )
            groups.setdefault(row_key, (group, group_title))
        per_sku.append(by_key)

    present = {key for m in per_sku for key in m}
    # Order: ATTR_GROUP_ORDER, then name within group.
    ordered_keys: list[str] = []
    by_group: dict[str, list[str]] = {g: [] for g in ATTR_GROUP_ORDER}
    by_group["other"] = []
    for key in present:
        group, _ = groups.get(key, ("other", "Прочие"))
        if group not in by_group:
            by_group.setdefault(group, [])
        by_group[group].append(key)
    for group in (*ATTR_GROUP_ORDER, "other"):
        keys = by_group.get(group) or []
        keys.sort(key=lambda k: (names.get(k) or k).casefold())
        ordered_keys.extend(keys)
    for group, keys in by_group.items():
        if group in ATTR_GROUP_ORDER or group == "other":
            continue
        keys.sort(key=lambda k: (names.get(k) or k).casefold())
        ordered_keys.extend(keys)

    rows: list[dict[str, Any]] = []
    for key in ordered_keys:
        values = [m.get(key, {}).get("cell", COMPARE_EMPTY_CELL) for m in per_sku]
        group, group_title = groups.get(key, ("other", "Прочие"))
        rows.append(
            {
                "key": key,
                "name": names.get(key, key),
                "group": group,
                "group_title": group_title,
                "values": values,
                "diff": _values_differ(values),
                "core": False,
            },
        )
    return rows


def _values_differ(values: list[str]) -> bool:
    """True when normalized cells are not all equal."""
    if len(values) < 2:
        return False
    norms = {normalize_compare_cell(v) for v in values}
    return len(norms) > 1


def _attr_lookup_keys(key: str) -> tuple[str, ...]:
    """Facet key ↔ attribute slug variants for gap-fill."""
    dashed = key.replace("_", "-")
    underscored = key.replace("-", "_")
    return tuple(dict.fromkeys((key, dashed, underscored)))


def _fill_empty_compare_cells_from_attributes(
    skus: list[SKU],
    rows: list[dict[str, Any]],
    *,
    serializer_context: dict[str, Any] | None = None,
) -> None:
    """Replace ``—`` core cells when the SKU still has the EAV value.

    List highlights are capped (Y/U signals eat slots), so mass/dimensions can
    drop from cards while remaining on the PDP attribute list — compare must
    not show a false gap.
    """
    context = serializer_context or {}
    per_sku: list[dict[str, str]] = []
    for sku in skus:
        by_key: dict[str, str] = {}
        for row in _sku_attribute_rows(sku, context):
            slug = str(row.get("slug") or "").strip()
            if not slug:
                continue
            cell = format_attribute_cell(row)
            if cell == COMPARE_EMPTY_CELL:
                continue
            for alias in _attr_lookup_keys(slug):
                by_key.setdefault(alias, cell)
        per_sku.append(by_key)

    for row in rows:
        values = row.get("values")
        if not isinstance(values, list):
            continue
        key = str(row.get("key") or "")
        aliases = _attr_lookup_keys(key)
        changed = False
        for index, value in enumerate(values):
            if value != COMPARE_EMPTY_CELL:
                continue
            if index >= len(per_sku):
                continue
            fill = next((per_sku[index][a] for a in aliases if a in per_sku[index]), None)
            if fill is None:
                continue
            values[index] = fill
            changed = True
        if changed:
            row["diff"] = _values_differ([str(v) for v in values])


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
        ``{"skus": [...], "rows": [...]}`` — core highlights first, then
        full attribute rows (``core=False``) for «Все характеристики».
    """
    context = serializer_context or {}
    payloads = SKUListSerializer(skus, many=True, context=context).data
    sku_list = [dict(item) for item in payloads]
    for item in sku_list:
        code = str(item.get("sku_code") or "").strip()
        if code:
            item["sku_code"] = code.upper()
    core_rows = build_compare_rows(sku_list)
    _fill_empty_compare_cells_from_attributes(
        skus,
        core_rows,
        serializer_context=context,
    )
    core_keys = {str(r["key"]) for r in core_rows}
    # Also skip underscore/dash variants of facet keys already covered as core,
    # plus legacy Y/U EAV aliases (control-signal-y / feedback-signal-u).
    expanded_skip = set(core_keys)
    for key in list(core_keys):
        expanded_skip.add(key.replace("_", "-"))
        expanded_skip.add(key.replace("-", "_"))
    expanded_skip.update(_SIGNAL_CORE_SKIP_SLUGS)
    for slug in _SIGNAL_CORE_SKIP_SLUGS:
        expanded_skip.add(slug.replace("-", "_"))
    attr_rows = build_attribute_compare_rows(
        skus,
        serializer_context=context,
        core_keys=expanded_skip,
    )
    return {
        "skus": sku_list,
        "rows": [*core_rows, *attr_rows],
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
