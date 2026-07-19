"""Extract raw records from Tilda catalog JSON payload.

Pure functions — no Django ORM. Yield raw dicts for the normalizer.
Spec: docs/data-quality-etl.md §1 (источник правды №1: hoocon_catalog_api.json).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def extract_products(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield raw product dicts from the Tilda API payload.

    Args:
        payload: parsed JSON from hoocon_catalog_api.json.

    Yields:
        Each entry from payload['products'].
    """
    products = payload.get("products") or []
    for product in products:
        if isinstance(product, dict):
            yield product


def extract_categories(
    payload: dict[str, Any],
) -> Iterator[tuple[int, str, int | None]]:
    """Yield (tilda_id, name, parent_tilda_id_or_None) from the Назначение filter.

    Walks the 'Назначение' filter tree (filters[0]) — top-level values + their
    subparts. Returns a flat list of (id, name, parent_id) tuples.

    Args:
        payload: parsed JSON from hoocon_catalog_api.json.

    Yields:
        Tuples (tilda_id, name, parent_tilda_id_or_None).
    """
    filters = (payload.get("filters") or {}).get("filters") or []
    if not filters:
        return

    purpose = next((f for f in filters if f.get("label") == "Назначение"), None)
    if purpose is None:
        return

    for value in purpose.get("values") or []:
        top_id = value.get("id")
        top_name = value.get("value") or ""
        if top_id is not None and top_name:
            yield (int(top_id), str(top_name), None)
        for sub in value.get("subparts") or []:
            sub_id = sub.get("id")
            sub_name = sub.get("value") or ""
            if sub_id is not None and sub_name:
                yield (int(sub_id), str(sub_name), int(top_id) if top_id else None)
