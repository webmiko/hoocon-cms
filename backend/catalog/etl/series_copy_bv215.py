"""Backward-compatible BV215 enricher — delegates to ball-valve series copy."""

from __future__ import annotations

from catalog.etl.series_copy_ball_valves import (
    apply_all_ball_valve_enrichment,
    format_bracket,
    format_compatible_actuators,
    load_ball_valve_series,
    product_slug_for_series,
)

PRODUCT_SLUG = product_slug_for_series("BV215")


def kvs_for_sku_code(sku_code: str) -> str | None:
    """Return Kvs for an 8100-bv215a…e edition (tests / callers)."""
    for series in load_ball_valve_series():
        if series.code != "BV215":
            continue
        from catalog.etl.series_copy_ball_valves import kvs_for_sku

        return kvs_for_sku(series, sku_code)
    return None


def apply_bv215_enrichment(*, import_images: bool = True) -> dict[str, int]:
    """Enrich only BV215 (same counters shape as before, without ``series``)."""
    stats = apply_all_ball_valve_enrichment(
        import_images=import_images,
        series_codes=("BV215",),
    )
    return {
        "products": stats["products"],
        "skus": stats["skus"],
        "attributes": stats["attributes"],
        "images_created": stats["images_created"],
        "images_failed": stats["images_failed"],
    }


__all__ = [
    "PRODUCT_SLUG",
    "apply_bv215_enrichment",
    "format_bracket",
    "format_compatible_actuators",
    "kvs_for_sku_code",
]
