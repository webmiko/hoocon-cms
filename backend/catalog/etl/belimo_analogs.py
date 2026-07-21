"""Belimo analog codes from card «Аналоги» text or ТТХ heuristics.

Used by the catalog «Аналоги» facet and ``SKU.analog_belimo_code`` backfill.
Prefer explicit Belimo lines in copy; otherwise infer a typical Belimo article
from purpose (category), damper torque/area band, voltage, control, aux SPDT.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal, cast

from catalog.etl.html_text import filter_analogs_for_sku
from catalog.etl.sku_variant import parse_sku_variant

if TYPE_CHECKING:
    from catalog.models import SKU, Category, Product

Purpose = Literal[
    "air_no_spring",
    "air_spring",
    "fire_spring",
    "fast",
    "smoke",
    "valve",
    "unknown",
]

# «– Belimo LF24-S» / «Belimo NF24A» / bare after brand.
_BELIMO_LINE = re.compile(
    r"(?i)\bBelimo\s+([A-Za-z][A-Za-z0-9./\-–—−]*)",
)
_TRAILING_PUNCT = re.compile(r"[.,;:]+$")
_HAS_230 = re.compile(r"(?:^|[^0-9])230(?:[^0-9]|$)")
_HAS_24 = re.compile(r"(?:^|[^0-9])24(?:[^0-9]|$)")
_MOMENT_NUM = re.compile(r"(\d+[.,]?\d*)")
_AREA_NUM = re.compile(r"(\d+[.,]?\d*)")

# Category slug fragments → purpose for inference.
_PURPOSE_BY_CATEGORY: tuple[tuple[str, Purpose], ...] = (
    ("uskoren", "fast"),
    ("dymoudalen", "smoke"),
    ("protivopozhar", "fire_spring"),
    ("pruzhinnym-vozvrat", "air_spring"),
    ("bez-pruzhinnogo", "air_no_spring"),
    ("vozdushn", "air_no_spring"),
    ("sharov", "valve"),
)


def normalize_belimo_code(raw: str) -> str:
    """Normalize a Belimo article token for facet keys.

    Args:
        raw: Raw token from copy (may include unicode dashes).

    Returns:
        Uppercase article with ASCII hyphens, no trailing punctuation.
    """
    code = (raw or "").strip().replace("\xa0", " ")
    code = code.replace("−", "-").replace("—", "-").replace("–", "-")
    code = _TRAILING_PUNCT.sub("", code)
    code = " ".join(code.split())
    return code.upper()


def extract_belimo_codes_from_text(
    text: str,
    *,
    voltage: str | None = None,
) -> list[str]:
    """Return unique Belimo article codes mentioned in analogs copy.

    Args:
        text: «Аналоги» tab / SKU analogs_text (plain).
        voltage: Optional ``24`` / ``230`` to drop mismatched articles.

    Returns:
        Ordered unique codes (first occurrence wins).
    """
    if not (text or "").strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in _BELIMO_LINE.finditer(text):
        code = normalize_belimo_code(match.group(1))
        if not _looks_like_belimo_article(code):
            continue
        if voltage and not code_matches_voltage(code, voltage):
            continue
        if code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def code_matches_voltage(code: str, voltage: str) -> bool:
    """Return False when article voltage clearly conflicts with SKU voltage."""
    has_230 = bool(_HAS_230.search(code))
    has_24 = bool(_HAS_24.search(code)) and not has_230
    if voltage == "24" and has_230:
        return False
    if voltage == "230" and has_24:
        return False
    return True


def _looks_like_belimo_article(code: str) -> bool:
    """Reject noise tokens after the Belimo brand word."""
    if len(code) < 3 or len(code) > 32:
        return False
    if not any(ch.isdigit() for ch in code):
        return False
    if not any(ch.isalpha() for ch in code):
        return False
    return True


def infer_belimo_codes(
    *,
    purpose: Purpose,
    moment_nm: float | None,
    voltage: str | None,
    control: str | None,
    aux_spdt: int,
    thermal: bool = False,
    damper_area_m2: float | None = None,
) -> list[str]:
    """Suggest typical Belimo article(s) from actuator purpose and ТТХ.

    Args:
        purpose: Actuator family inferred from category / SKU code.
        moment_nm: Rated torque in N·m (preferred).
        voltage: ``24`` or ``230``.
        control: ``on_off`` / ``modulating`` / ``3_point`` (treated as on_off).
        aux_spdt: 0 / 1 / 2 auxiliary SPDT switches.
        thermal: Fire actuator with thermal fuse (DST / -T).
        damper_area_m2: Fallback when moment is missing.

    Returns:
        Zero or one primary Belimo code (list for API symmetry).
    """
    if purpose in {"valve", "unknown"} or not voltage:
        return []

    nm = moment_nm
    if nm is None and damper_area_m2 is not None:
        # Rough HVAC rule of thumb: ~10 N·m per m².
        nm = round(damper_area_m2 * 10, 1)
    if nm is None:
        return []

    modulating = control == "modulating"
    family = _belimo_family(purpose, nm)
    if not family:
        return []

    code = _compose_belimo_article(
        family=family,
        voltage=voltage,
        modulating=modulating,
        aux_spdt=aux_spdt,
        thermal=thermal,
        purpose=purpose,
        moment_nm=nm,
    )
    return [code] if code else []


def _belimo_family(purpose: Purpose, moment_nm: float) -> str | None:
    """Map purpose + torque band to Belimo series letters."""
    if purpose == "air_no_spring":
        if moment_nm <= 6:
            return "LM"
        if moment_nm <= 12:
            return "NM"
        if moment_nm <= 25:
            return "SM"
        return "GM"
    if purpose == "air_spring":
        if moment_nm <= 6:
            return "LF"
        if moment_nm <= 12:
            return "NF"
        return "SF"
    if purpose == "fire_spring":
        if moment_nm <= 6:
            return "BF"
        if moment_nm <= 12:
            return "BFN"
        return "BFS"
    if purpose == "fast":
        if moment_nm <= 6:
            return "BM"
        return "NMQ"
    if purpose == "smoke":
        return "CM"
    return None


def _compose_belimo_article(
    *,
    family: str,
    voltage: str,
    modulating: bool,
    aux_spdt: int,
    thermal: bool,
    purpose: Purpose,
    moment_nm: float,
) -> str | None:
    """Build a Belimo-like article string for facet matching."""
    if purpose == "fast" and family == "BM":
        # Card copy for HVA uses BM24-5-05 / BM230-5-05.
        base = f"BM{voltage}-5-05"
        return base

    if purpose == "smoke":
        # CM24-L/R style from smoke-removal cards.
        return f"CM{voltage}-L/R"

    if purpose == "fast" and family == "NMQ":
        code = f"NMQ{voltage}A"
        if modulating:
            code += "-SR"
        if aux_spdt >= 1:
            code += "-S"
        return code

    if purpose == "fire_spring":
        code = f"{family}{voltage}"
        if aux_spdt >= 1:
            code += "-S"
        if thermal:
            code += "-T"
        return code

    if purpose == "air_spring":
        # NF24A / LF24-S / SF24A pattern from existing cards.
        if family == "LF":
            code = f"LF{voltage}"
            if aux_spdt >= 1:
                code += "-S"
            return code
        code = f"{family}{voltage}A"
        if modulating:
            code += "-SR" if family != "NF" else "-A"
        if aux_spdt >= 1 and not code.endswith("-S"):
            code += "-S"
        return code

    # Classic non-spring LM/NM/SM/GM.
    code = f"{family}{voltage}A"
    if modulating:
        code += "-SR"
    if aux_spdt >= 1:
        code += "-S"
    return code


def detect_purpose(*, category_slug: str, sku_code: str) -> Purpose:
    """Infer actuator purpose from category slug and SKU code."""
    slug = (category_slug or "").casefold()
    code = (sku_code or "").casefold()
    for fragment, purpose in _PURPOSE_BY_CATEGORY:
        if fragment in slug:
            return purpose
    if code.startswith("sa") and "fu" in code:
        return "fire_spring"
    if "mqu" in code or code.startswith("hva"):
        return "fast"
    if code.startswith("hvd") or "mu" in code:
        return "air_no_spring"
    if "fu" in code:
        return "air_spring"
    if code.startswith("bv") or "8100" in code:
        return "valve"
    return "unknown"


def analogs_plain_text_for_sku(sku: SKU) -> str:
    """Edition-scoped analogs plain text (SKU or product tab)."""
    # Bare ForeignKey annotations on SKU.product type as ``_ST`` in django-stubs.
    product = cast("Product", sku.product)
    raw = (sku.analogs_text or "") or (product.analogs_text or "")
    if not raw.strip():
        return ""
    return filter_analogs_for_sku(raw, sku.sku_code)


def belimo_codes_for_sku(sku: SKU) -> list[str]:
    """Resolve Belimo codes for a SKU: card text first, else ТТХ inference.

    Args:
        sku: Catalog SKU (product + category + EAV used when inferring).

    Returns:
        Ordered unique Belimo article codes.
    """
    variant = parse_sku_variant(sku.sku_code)
    voltage = variant.voltage
    text = analogs_plain_text_for_sku(sku)
    from_text = extract_belimo_codes_from_text(text, voltage=voltage)
    if from_text:
        aux = _resolve_aux_switch(variant.aux_switch, sku.sku_code)
        return _filter_codes_by_aux(from_text, aux)

    stored = (sku.analog_belimo_code or "").strip()
    if stored:
        # Explicit field wins over inference (may be set by admin / fill command).
        return [normalize_belimo_code(stored)]

    return _infer_for_sku(sku, voltage=voltage)


def _resolve_aux_switch(parsed: bool | None, sku_code: str) -> bool | None:
    """Edition aux flag from SKU code when ``parse_sku_variant`` left it None."""
    if parsed is not None:
        return parsed
    code = (sku_code or "").casefold()
    # HVD24S-20 / HVA24S-5Q — «S» before torque means aux switches.
    if re.search(r"(?:hvd|hva)\d+s", code):
        return True
    if re.search(r"(?:hvd|hva)\d", code):
        return False
    return None


def _filter_codes_by_aux(codes: list[str], aux_switch: bool | None) -> list[str]:
    """Drop the mismatched side of BASE / BASE-S pairs only.

    Unrelated articles (``LF24-S`` + ``LF24-RS``) are kept together.
    """
    if aux_switch is None or len(codes) <= 1:
        return codes
    drop: set[str] = set()
    for code in codes:
        if not re.search(r"-S\d?$", code, re.I):
            continue
        base = re.sub(r"-S\d?$", "", code, flags=re.I)
        if base not in codes:
            continue
        if aux_switch:
            drop.add(base)
        else:
            drop.add(code)
    if not drop:
        return codes
    return [code for code in codes if code not in drop]


def primary_belimo_code_for_sku(sku: SKU) -> str | None:
    """First Belimo code for ``SKU.analog_belimo_code`` persistence.

    Thermal editions (``DST`` / ``-T`` in the Hoocon article) must map to a
    thermal Belimo code (``FST`` / ``-T``). If none is present among resolved
    codes, return ``None`` rather than a non-thermal fallback.
    """
    codes = belimo_codes_for_sku(sku)
    if not codes:
        return None
    code_l = (sku.sku_code or "").casefold()
    thermal = "dst" in code_l or code_l.endswith("-t")
    if not thermal:
        return codes[0]
    for code in codes:
        upper = code.upper()
        if "FST" in upper or upper.endswith("-T") or "-T" in upper:
            return code
    return None


def _infer_for_sku(sku: SKU, *, voltage: str | None) -> list[str]:
    """Build inference inputs from EAV / variant and call ``infer_belimo_codes``."""
    category_slug = ""
    if sku.product_id:
        product = cast("Product", sku.product)
        if product.category_id:
            category = cast("Category", product.category)
            category_slug = category.slug or ""
    purpose = detect_purpose(category_slug=category_slug, sku_code=sku.sku_code)
    if purpose in {"valve", "unknown"}:
        return []

    attrs = _sku_attr_map(sku)
    variant = parse_sku_variant(sku.sku_code)
    volt = voltage or variant.voltage or _voltage_from_attr(attrs.get("voltage", ""))
    control = variant.control or _control_from_attr(attrs.get("control", ""))
    aux = _aux_spdt_from_attr(attrs.get("aux-switch", ""), sku_code=sku.sku_code)
    if aux is None:
        aux = 1 if variant.aux_switch else 0
    moment = _parse_float(attrs.get("moment", ""))
    area = _parse_area(attrs.get("damper-area", ""))
    thermal = bool(re.search(r"dst$|-t$", (sku.sku_code or "").casefold()))
    return infer_belimo_codes(
        purpose=purpose,
        moment_nm=moment,
        voltage=volt,
        control=control,
        aux_spdt=aux or 0,
        thermal=thermal,
        damper_area_m2=area,
    )


def _sku_attr_map(sku: SKU) -> dict[str, str]:
    """Slug → value for inference (prefetched when available).

    First occurrence of each slug wins (keeps the earlier AttributeValue).
    Opaque Tilda ``attr-*`` slugs are aliased to canonical keys via names below.
    """
    values = getattr(sku, "_prefetched_attribute_values", None)
    if values is None:
        values = list(sku.attribute_values.select_related("attribute"))
    out: dict[str, str] = {}
    for av in values:
        slug = (av.attribute.slug or "").casefold()
        if not slug or slug in out:
            continue
        out[slug] = str(av.value or "")
    # Alias opaque Tilda slugs by attribute name when needed.
    for av in values:
        name = (av.attribute.name or "").casefold()
        if "крутящий момент" in name or name == "момент":
            out.setdefault("moment", str(av.value or ""))
        elif "напряжен" in name and "диапазон" not in name:
            out.setdefault("voltage", str(av.value or ""))
        elif name == "управление" or name.startswith("управление "):
            out.setdefault("control", str(av.value or ""))
        elif "вспомогательн" in name:
            out.setdefault("aux-switch", str(av.value or ""))
        elif "площад" in name:
            out.setdefault("damper-area", str(av.value or ""))
    return out


def _voltage_from_attr(value: str) -> str | None:
    if _HAS_230.search(value or ""):
        return "230"
    if _HAS_24.search(value or ""):
        return "24"
    return None


def _control_from_attr(value: str) -> str | None:
    low = (value or "").casefold()
    if "пропорционал" in low or "модулир" in low:
        return "modulating"
    if "открыто" in low or "2-" in low or "3-" in low or "позицион" in low:
        return "on_off"
    return None


def _aux_spdt_from_attr(value: str, *, sku_code: str) -> int | None:
    """Parse SPDT count from EAV without importing facets (avoid cycles)."""
    low = (value or "").casefold().strip()
    if not low or low in {"нет", "no", "0", "-", "—", "–"}:
        return 0
    if "spdt-2" in low or re.search(r"\b2\b", low):
        return 2
    if "spdt-1" in low or re.search(r"\b1\b", low) or "да" in low:
        return 1
    # Edition suffix AS/S often means two switches on modulating air SKUs.
    code = (sku_code or "").casefold()
    if re.search(r"-as(?:$|[^a-z])", code) or code.endswith("-as"):
        return 2
    if re.search(r"-ds(?:$|[^a-z])", code) or code.endswith(("-ds", "-s")):
        return 1
    return None


def _parse_float(value: str) -> float | None:
    match = _MOMENT_NUM.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _parse_area(value: str) -> float | None:
    match = _AREA_NUM.search(value or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None
