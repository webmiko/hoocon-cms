"""SKU-scoped install guides for public PDP (all actuator series).

Prefer a series builder (torque / voltage / aux / thermal). Fall back to
filtering stored Product/Category ``instructions`` by SKU variant.
"""

from __future__ import annotations

from collections.abc import Callable

from catalog.etl.sku_variant import (
    SkuVariant,
    filter_description_for_variant,
    parse_sku_variant,
)

_Builder = Callable[[str], str | None]


def format_damper_area(raw: str) -> str:
    """Ensure damper-area phrase includes ``м²`` once."""
    text = (raw or "").strip()
    if not text:
        return text
    if "м²" in text or "м2" in text.casefold():
        return text
    return f"{text} м²"


def power_supply_bullets(variant: SkuVariant, *, class_ii_detail: bool = False) -> list[str]:
    """Voltage-scoped питание bullets for install guides."""
    class_ii = "класс защиты II — полная изоляция" if class_ii_detail else "класс защиты II"
    if variant.voltage == "24":
        return ["– Питание: AC/DC 24 В, 50/60 Гц (класс защиты III)."]
    if variant.voltage == "230":
        return [f"– Питание: AC 100…240 В, 50/60 Гц ({class_ii})."]
    return [
        "– Исполнения 24 В: AC/DC 24 В, 50/60 Гц (класс защиты III).",
        f"– Исполнения 230 В: AC 100…240 В, 50/60 Гц ({class_ii}).",
    ]


def instructions_for_sku(sku_code: str, *, stored_text: str = "") -> str:
    """Return install guide text for one catalog SKU.

    Args:
        sku_code: Edition code (``DA4MU24-D``, ``SA5FU230-DST``, …).
        stored_text: Category/product instructions when no series builder matches
            (Tilda scrape, ball valves, …).

    Returns:
        Normalized plain text, or ``""`` when nothing applies.
    """
    code = (sku_code or "").strip()
    if not code:
        if not (stored_text or "").strip():
            return ""
        return filter_description_for_variant(stored_text, parse_sku_variant(""))

    for builder in _builders():
        built = builder(code)
        if built:
            return built

    if not (stored_text or "").strip():
        return ""
    return filter_description_for_variant(stored_text, parse_sku_variant(code))


def _builders() -> tuple[_Builder, ...]:
    """Lazy imports avoid circular loads among series_copy modules."""
    from catalog.etl.series_copy_dafu import instructions_for_dafu_sku
    from catalog.etl.series_copy_damu import instructions_for_damu_sku
    from catalog.etl.series_copy_hvdf import instructions_for_hvdf_sku
    from catalog.etl.series_copy_safu import instructions_for_safu_sku
    from catalog.etl.series_copy_samu import instructions_for_samu_sku

    return (
        instructions_for_damu_sku,
        instructions_for_dafu_sku,
        instructions_for_safu_sku,
        instructions_for_samu_sku,
        instructions_for_hvdf_sku,
    )
