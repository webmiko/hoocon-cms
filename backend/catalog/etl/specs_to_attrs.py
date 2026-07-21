"""Parse SKU/product ``specs_text`` into canonical AttributeValue cards.

Used by ``enrich_catalog_cards`` to unify PDP ТТХ with the DA8MQU card layout.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.html_text import dedupe_description_lines
from catalog.etl.label_to_slug import CANONICAL_ATTRS, canonical_meta, label_to_slug
from catalog.etl.series_copy_ball_valves import ball_valve_product_slugs
from catalog.etl.sku_variant import filter_description_for_variant, parse_sku_variant
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import SKU, Product

logger = logging.getLogger(__name__)

DA8MQU_PRODUCT_SLUG = "privod-vozdushniy-da8mqu-8nm"
CANONICAL_CARD_PRODUCT_SLUGS: frozenset[str] = frozenset(
    {DA8MQU_PRODUCT_SLUG, *ball_valve_product_slugs()},
)

_BULLET_LINE = re.compile(
    r"^\s*(?:[-–—•*]|\d+[.)]\s*)\s*(?P<body>.+)$",
)
_LABEL_VALUE = re.compile(
    r"^(?P<label>[^:]{2,80}?)\s*:\s*(?P<value>.+)$",
)
_MODEL_HEADER = re.compile(
    r"^[A-Z]{1,6}\d{0,3}[A-Z0-9./\-]*\s*:",
    re.I,
)
_SHOW_MORE = re.compile(r"показать весь текст", re.I)

# Min attrs before we clear specs_text.
MIN_ATTRS_ACTUATOR = 8
MIN_ATTRS_VALVE = 3

_VALVE_SKU = re.compile(r"(?i)bv\d|8100-bv")


@dataclass
class ParsedAttr:
    """One canonical attribute candidate from specs prose."""

    slug: str
    name: str
    unit: str
    value: str


@dataclass
class EnrichResult:
    """Per-SKU enrich outcome."""

    sku_code: str
    attrs_before: int = 0
    attrs_after: int = 0
    cleared_specs: bool = False
    skipped: bool = False
    reason: str = ""
    slugs: list[str] = field(default_factory=list)


def parse_specs_bullets(text: str) -> list[ParsedAttr]:
    """Extract ``Label: value`` bullets into canonical attrs.

    Args:
        text: Variant-filtered specs prose.

    Returns:
        Deduped list (later lines override earlier for same slug).
    """
    if not text or not text.strip():
        return []
    text = normalize_tech_copy(text.replace("\xa0", " "))
    text = _SHOW_MORE.sub("", text)
    by_slug: dict[str, ParsedAttr] = {}
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or len(line) < 4:
            continue
        if _MODEL_HEADER.match(line) and ":" in line and len(line) < 40:
            continue
        body = line
        bullet = _BULLET_LINE.match(line)
        if bullet:
            body = bullet.group("body").strip()
        match = _LABEL_VALUE.match(body)
        if not match:
            continue
        label = match.group("label").strip()
        value = match.group("value").strip()
        if not value or value in {"–", "-", "—"}:
            continue
        slug = label_to_slug(label, value=value)
        if not slug:
            continue
        meta = canonical_meta(slug)
        if meta is None:
            continue
        name, unit, _group = meta
        value = _normalize_value(slug, value)
        by_slug[slug] = ParsedAttr(slug=slug, name=name, unit=unit, value=value)
    return list(by_slug.values())


def _normalize_value(slug: str, value: str) -> str:
    """Light Belimo-RU cleanup for stored values."""
    v = " ".join(value.split())
    v = v.replace("VDC", "В=").replace("vdc", "В=")
    v = re.sub(r"\b(\d)\s*V\b", r"\1 В", v)
    v = re.sub(r"\b(\d+[.,]?\d*)\s*W\b", r"\1 Вт", v, flags=re.I)
    v = re.sub(r"\b(\d+)\s*VA\b", r"\1 В·А", v, flags=re.I)
    v = re.sub(r"\b(\d+)\s*Hz\b", r"\1 Гц", v, flags=re.I)
    v = v.replace("ожидание", "удержание")
    if slug == "protection-class":
        low = v.casefold()
        if "iii" in low or "iii" in v or "Ⅲ" in v or re.search(r"\bIII\b", v):
            return "III (безопасное сверхнизкое напряжение)"
        if "ii" in low or "Ⅱ" in v or re.search(r"\bII\b", v):
            return "II (все изолировано / полная изоляция)"
    if slug == "ip-rating":
        m = re.search(r"IP\s*(\d{2})", v, re.I)
        if m:
            return f"IP{m.group(1)}"
    if slug == "aux-switch":
        low = v.casefold()
        if any(x in low for x in ("нет", "без", "отсутств", "0")):
            return "Нет"
        if any(x in low for x in ("да", "есть", "2", "spdt", "шт")):
            return "Да"
    return v


def _set_attr(sku: SKU, slug: str, value: str) -> None:
    meta = canonical_meta(slug)
    if meta is None:
        return
    name, unit, _ = meta
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _migrate_legacy_attrs(sku: SKU) -> dict[str, str]:
    """Map existing hash/legacy AttributeValues onto canonical slugs."""
    found: dict[str, str] = {}
    for av in sku.attribute_values.select_related("attribute"):
        slug = av.attribute.slug
        name = av.attribute.name or ""
        value = str(av.value).strip()
        if slug in CANONICAL_ATTRS:
            found[slug] = value
            continue
        if slug.startswith("kvs"):
            found.setdefault("kvs", value)
            continue
        if slug == "dn":
            found.setdefault("dn", value)
            continue
        mapped = label_to_slug(name, value=value)
        # Mirror parse_specs_bullets: only keep slugs known to CANONICAL_ATTRS.
        if mapped and canonical_meta(mapped) is not None:
            found.setdefault(mapped, value)
    return found


def _apply_variant_overrides(sku: SKU, by_slug: dict[str, str]) -> None:
    """Fill voltage / control / aux from SKU code when missing."""
    variant = parse_sku_variant(sku.sku_code)
    if variant.voltage == "24" and "voltage" not in by_slug:
        by_slug["voltage"] = "AC/DC 24 В, 50/60 Гц"
    elif variant.voltage == "230" and "voltage" not in by_slug:
        by_slug["voltage"] = "AC 100…240 В, 50/60 Гц"
    if variant.control == "modulating" and "control" not in by_slug:
        from catalog.etl.tech_copy import CONTROL_MODULATING

        by_slug["control"] = CONTROL_MODULATING
    elif variant.control == "on_off" and "control" not in by_slug:
        from catalog.etl.tech_copy import normalize_control_attribute_value
        from catalog.sku_access import sku_category_slug_or_empty

        by_slug["control"] = normalize_control_attribute_value(
            "2-/3-позиционное",
            sku_code=sku.sku_code,
            category_slug=sku_category_slug_or_empty(sku),
        )
    if variant.aux_switch is True and "aux-switch" not in by_slug:
        from catalog.facets import aux_spdt_count_from_sku, normalize_aux_switch_value

        count = aux_spdt_count_from_sku(sku.sku_code) or 2
        by_slug["aux-switch"] = normalize_aux_switch_value(
            f"SPDT-{count}",
            sku_code=sku.sku_code,
        )
    elif variant.aux_switch is False:
        # Absent → omit (never store «Нет»).
        by_slug.pop("aux-switch", None)

    # Drop legacy «Нет» / empty aux values from specs parse.
    from catalog.facets import AUX_SWITCH_NONE, format_aux_switch_display

    aux_raw = by_slug.get("aux-switch")
    if aux_raw is not None:
        formatted = format_aux_switch_display(
            aux_raw,
            sku_code=sku.sku_code,
            description=sku.description or "",
        )
        if formatted is None or formatted == AUX_SWITCH_NONE:
            by_slug.pop("aux-switch", None)
        else:
            by_slug["aux-switch"] = formatted


def _valve_from_sku_code(sku: SKU, by_slug: dict[str, str]) -> None:
    """Infer DN / ways from BV article when specs are empty."""
    code = (sku.sku_code or "").upper()
    name = (sku.name or "").casefold()
    if not _VALVE_SKU.search(code) and "шаровой" not in name:
        return
    if "dn" not in by_slug:
        m = re.search(r"DN\s*(\d+)", sku.name or "", re.I)
        if not m:
            m = re.search(r"BV([23])(\d{2})", code)
            if m:
                by_slug["dn"] = str(int(m.group(2)))
        else:
            by_slug["dn"] = m.group(1)
    if "ways" not in by_slug:
        if "3-ходов" in name or re.search(r"BV3", code):
            by_slug["ways"] = "3-ходовый"
        elif "2-ходов" in name or re.search(r"BV2", code):
            by_slug["ways"] = "2-ходовый"


def _is_valve_sku(sku: SKU) -> bool:
    code = (sku.sku_code or "").upper()
    name = (sku.name or "").casefold()
    return bool(_VALVE_SKU.search(code) or "шаровой" in name or "кран" in name)


def _specs_source(sku: SKU) -> str:
    from catalog.sku_access import sku_section_text

    return dedupe_description_lines(sku_section_text(sku, "specs_text"))


def _sku_ready_for_card_enrichment(sku: SKU) -> bool:
    """True when product (+ category) and attribute_values are cached."""
    fields_cache = sku._state.fields_cache
    if "product" not in fields_cache:
        return False
    product = fields_cache["product"]
    if product is not None and product.category_id:
        if "category" not in product._state.fields_cache:
            return False
    prefetched = getattr(sku, "_prefetched_objects_cache", None) or {}
    return "attribute_values" in prefetched


def _load_sku_for_card_enrichment(sku: SKU) -> SKU:
    """Ensure product/category and EAV are loaded (avoids N+1 for callers).

    Args:
        sku: SKU instance (may be bare or already select_related).

    Returns:
        Same instance when relations are cached; otherwise a refetch.
    """
    if _sku_ready_for_card_enrichment(sku):
        return sku
    return (
        SKU.objects.select_related("product", "product__category")
        .prefetch_related("attribute_values__attribute")
        .get(pk=sku.pk)
    )


def enrich_sku_cards(sku: SKU, *, dry_run: bool = False) -> EnrichResult:
    """Build canonical EAV cards for one SKU from specs + legacy attrs.

    Args:
        sku: Target SKU. Prefer ``select_related("product", "product__category")``
            and prefetched ``attribute_values``; otherwise this function refetches.
        dry_run: If True, do not write DB.

    Returns:
        EnrichResult counters.
    """
    sku = _load_sku_for_card_enrichment(sku)
    result = EnrichResult(sku_code=sku.sku_code)
    from catalog.sku_access import sku_product

    product = sku_product(sku)
    if product is not None and product.slug in CANONICAL_CARD_PRODUCT_SLUGS:
        result.skipped = True
        result.reason = "canonical_series_copy"
        return result
    if product is None:
        result.skipped = True
        result.reason = "missing_product"
        return result

    result.attrs_before = sku.attribute_values.count()
    variant = parse_sku_variant(sku.sku_code)
    raw = _specs_source(sku)
    filtered = filter_description_for_variant(raw, variant) if raw else ""
    parsed = parse_specs_bullets(filtered)
    by_slug: dict[str, str] = {p.slug: p.value for p in parsed}
    by_slug.update({k: v for k, v in _migrate_legacy_attrs(sku).items() if k not in by_slug})
    _apply_variant_overrides(sku, by_slug)
    _valve_from_sku_code(sku, by_slug)

    result.slugs = sorted(by_slug)
    result.attrs_after = len(by_slug)

    min_needed = MIN_ATTRS_VALVE if _is_valve_sku(sku) else MIN_ATTRS_ACTUATOR
    if dry_run:
        result.cleared_specs = result.attrs_after >= min_needed and bool(raw)
        return result

    # Rewrite EAV: keep only canonical slugs for this SKU.
    keep_slugs = set(by_slug)
    for av in list(sku.attribute_values.select_related("attribute")):
        if av.attribute.slug not in keep_slugs:
            av.delete()

    for slug, value in by_slug.items():
        _set_attr(sku, slug, value)

    if result.attrs_after >= min_needed:
        if (sku.specs_text or "").strip():
            sku.specs_text = ""
            sku.save(update_fields=["specs_text"])
            result.cleared_specs = True
        # Trim description ТТХ bullets that duplicate cards (keep control lines).
        desc = sku.description or ""
        if desc.strip():
            from catalog.facets import strip_attribute_echo_from_text

            rows = [{"name": CANONICAL_ATTRS[s][0], "value": v} for s, v in by_slug.items() if s in CANONICAL_ATTRS]
            # Re-append control/aux bullets after strip.
            stripped = strip_attribute_echo_from_text(desc, rows)
            extras: list[str] = []
            if "control" in by_slug:
                extras.append(f"– Управление: {by_slug['control']}")
            if str(by_slug.get("aux-switch") or "").upper().startswith("SPDT"):
                extras.append(
                    f"– Вспомогательный переключатель: {by_slug['aux-switch']}.",
                )
            new_desc = stripped
            if extras:
                new_desc = (stripped + "\n" + "\n".join(extras)).strip() if stripped else "\n".join(extras)
            if new_desc != desc:
                sku.description = new_desc
                sku.save(update_fields=["description"])

    return result


def maybe_clear_product_specs(product: Product) -> bool:
    """Clear product.specs_text when all child SKUs have empty specs_text."""
    skus = list(product.skus.all())
    if not skus:
        return False
    if all(not (s.specs_text or "").strip() for s in skus):
        if (product.specs_text or "").strip():
            product.specs_text = ""
            product.save(update_fields=["specs_text"])
            return True
    return False


def enrich_catalog_cards(
    *,
    product_slug: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Enrich all (or one product's) SKUs into grouped card EAV.

    Args:
        product_slug: Optional Product.slug filter.
        dry_run: Report only.

    Returns:
        Summary dict with counts and per-SKU results.
    """
    qs = SKU.objects.select_related("product", "product__category").prefetch_related(
        "attribute_values__attribute",
    )
    if product_slug:
        qs = qs.filter(product__slug=product_slug)
    results: list[EnrichResult] = []
    for sku in qs.iterator(chunk_size=50):
        # Re-fetch with relations for writes (iterator drops prefetch cache).
        sku = (
            SKU.objects.select_related("product", "product__category")
            .prefetch_related(
                "attribute_values__attribute",
            )
            .get(pk=sku.pk)
        )
        results.append(enrich_sku_cards(sku, dry_run=dry_run))

    if not dry_run:
        products = Product.objects.all()
        if product_slug:
            products = products.filter(slug=product_slug)
        for product in products:
            if product.slug in CANONICAL_CARD_PRODUCT_SLUGS:
                continue
            maybe_clear_product_specs(product)

    enriched = [r for r in results if not r.skipped]
    return {
        "total": len(results),
        "skipped": sum(1 for r in results if r.skipped),
        "enriched": len(enriched),
        "cleared_specs": sum(1 for r in enriched if r.cleared_specs),
        "avg_attrs": (round(sum(r.attrs_after for r in enriched) / len(enriched), 1) if enriched else 0),
        "results": results,
    }
