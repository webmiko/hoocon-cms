"""Sibling edition payloads for multi-SKU Product cards
(H81 / brass / LAV / DAMU / SAMU / SAFU / HVA / HVD)."""

from __future__ import annotations

from typing import Any

from catalog.etl.h81_kits import body_meta_for_h81, parse_h81_kit_parts
from catalog.etl.h8205_lav import parse_h8205_sku_parts
from catalog.etl.series_copy_ball_valves import body_meta_for_brass, brass_body_code_from_sku
from catalog.etl.sku_variant import parse_sku_variant, sku_code_is_thermal
from catalog.models import SKU


def sibling_edition_row(sku: SKU) -> dict[str, Any]:
    """Build one sibling row for the PDP variant picker.

    Args:
        sku: Published (or any) catalog SKU.

    Returns:
        Dict with slug, sku_code, axes fields, and stock flag.
    """
    code = (sku.sku_code or "").strip()
    variant = parse_sku_variant(code)
    dn = ""
    ways = ""
    kvs = ""
    body = ""
    h81 = parse_h81_kit_parts(code)
    if h81 is not None:
        body = h81["body"]
        meta = body_meta_for_h81(h81["kit"], body)
        if meta is not None:
            dn, kvs, ways = meta
    else:
        lav = parse_h8205_sku_parts(code)
        if lav is not None:
            body = lav["body"]
            # LAV232 → DN from digits after ways digit.
            digits = "".join(ch for ch in body[4:] if ch.isdigit())
            dn = digits
            ways = "2-ходовый" if body.startswith("LAV2") else "3-ходовый"
        else:
            brass_body = brass_body_code_from_sku(code)
            if brass_body is not None:
                body = brass_body
                meta = body_meta_for_brass(brass_body)
                if meta is not None:
                    dn, kvs, ways = meta

    ctrl = variant.control or ""
    if ctrl == "modulating":
        control_key = "A" if not variant.aux_switch else "AS"
    elif ctrl == "on_off":
        # SA thermal editions share on_off+aux with DS; keep DST distinct for picker.
        if sku_code_is_thermal(code):
            control_key = "DST"
        else:
            control_key = "D" if not variant.aux_switch else "DS"
    elif ctrl == "modbus":
        control_key = "M"
    else:
        control_key = ""

    return {
        "slug": sku.slug,
        "sku_code": code,
        "body": body,
        "dn": dn,
        "ways": ways,
        "kvs": kvs,
        "voltage": variant.voltage or "",
        "control": control_key,
        "aux_switch": bool(variant.aux_switch),
        "fault_alarm": bool(variant.fault_alarm),
        "in_stock": bool(sku.in_stock),
    }


def siblings_for_sku(sku: SKU, *, limit: int = 400) -> list[dict[str, Any]]:
    """Return edition rows for all published SKUs on the same Product.

    Args:
        sku: Current PDP SKU.
        limit: Cap (H8101 has 288 editions).

    Returns:
        Sorted sibling rows (by sku_code).
    """
    if not sku.product_id:
        return []
    qs = (
        SKU.objects.filter(product_id=sku.product_id, is_published=True)
        .only("slug", "sku_code", "stock_qty")
        .order_by("sku_code")[:limit]
    )
    return [sibling_edition_row(row) for row in qs]


def variant_axes_from_siblings(siblings: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Unique axis values for the PDP picker (ordered).

    Args:
        siblings: Output of :func:`siblings_for_sku`.

    Returns:
        Dict of axis → ordered unique values.
    """

    def _uniq(key: str) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for row in siblings:
            val = str(row.get(key) or "").strip()
            if not val or val in seen:
                continue
            seen.add(val)
            out.append(val)
        return out

    return {
        "ways": _uniq("ways"),
        "dn": sorted(_uniq("dn"), key=lambda x: int(x) if x.isdigit() else 0),
        "kvs": _uniq("kvs"),
        "body": _uniq("body"),
        "voltage": _uniq("voltage"),
        "control": _uniq("control"),
    }
