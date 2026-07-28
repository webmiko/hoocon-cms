"""Canonical copy + ТТХ for Hoocon DA..MQU (fast damper, no spring return).

Sources: DA8MQU datasheet (legacy 8 Нм) + 2022 Russian AI album
(``浒江2022俄文画册2.ai``) for DA5 / DA10 / DA20MQU.
Characteristics are stored as EAV rows with group keys for PDP cards.
"""

from __future__ import annotations

import re
from typing import Any, Final

from django.db.models import QuerySet

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant, torque_nm_from_sku_code
from catalog.etl.tech_copy import (
    CONTROL_MODULATING,
    CONTROL_SIGNAL_Y_CANON,
    CONTROL_SIGNAL_Y_LABEL,
    CONTROL_SIGNAL_Y_SLUG,
    FEEDBACK_SIGNAL_U_CANON,
    FEEDBACK_SIGNAL_U_LABEL,
    FEEDBACK_SIGNAL_U_SLUG,
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.models import SKU, AttributeValue, Product

# Legacy single-product slug (kept for tests / redirects).
PRODUCT_SLUG = "privod-vozdushniy-da8mqu-8nm"

_PRODUCT_SLUG_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^privod-vozdushniy-da\d+mqu-\d+nm$",
)
_SKU_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^da(?P<nm>\d+)mqu(?:24|230)-(?:as|ds|a|d)$",
)

PRODUCT_NAME_TMPL = "DA{nm}MQU | Электропривод воздушный ускоренного срабатывания без возвратной пружины, {nm} Нм"

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод воздушной заслонки ускоренного срабатывания
без возвратной пружины. Используется в воздушных клапанах
систем ОВК (отопления, вентиляции и кондиционирования).

Назначение и особенности серии DA..MQU:
– Управление воздушными заслонками и клапанами в системах
  приточной, вытяжной и приточно-вытяжной вентиляции,
  кондиционирования и отопления.
– Без возвратной пружины: положение заслонки фиксируется
  при отключении питания.
– Время поворота: ускоренное (см. ТТХ выбранного артикула).
– Крутящий момент: 5…20 Нм (DA5MQU, DA8MQU, DA10MQU, DA20MQU).
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –20…+50 °C.

Область применения:
– Общеобменная вентиляция (офисы, торговые центры).
– Спецобъекты: аэропорты, метро, ТЭЦ, мед. учреждения, фермы.
– Центральное кондиционирование и отопление.

Управление по исполнению:
– Пропорциональное (модулирующее) 0…10 В=: суффиксы -A / -AS.
– 2-/3-позиционное: суффиксы -D / -DS.
– Вспомогательные переключатели 2 SPDT: суффиксы -AS / -DS.
""".strip(),
)

# name, slug, unit, value, group_key — shared across Nm (edition overrides below).
AttrRow = tuple[str, str, str, str, str]

_SHARED_BASE: tuple[AttrRow, ...] = (
    (
        "Сечение клемм",
        "terminal-size",
        "мм²",
        "макс. 2,0",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Направление вращения",
        "rotation-direction",
        "",
        "задаётся вручную",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Ручное управление",
        "manual-override",
        "",
        MANUAL_OVERRIDE_BUTTON_SELF_RESET,
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Угол поворота",
        "rotation-angle",
        "°",
        "макс. 90°",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Индикация положения",
        "position-indication",
        "",
        "механическая",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Степень защиты корпуса",
        "ip-rating",
        "",
        "IP54",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура окружающей среды",
        "ambient-temp",
        "°C",
        "–20…+50 (IEC 721-3-3)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура хранения",
        "storage-temp",
        "°C",
        "–30…+80 (IEC 721-3-2)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Относительная влажность",
        "humidity",
        "",
        "95 %, без конденсата (EN 60730-1)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Длина вала заслонки",
        "shaft-length",
        "мм",
        "≥ 50",
        ATTR_GROUP_SIZE,
    ),
    (
        "Сечение провода",
        "wire-cross-section",
        "мм²",
        "0,5",
        ATTR_GROUP_ELECTRICAL,
    ),
)

_DIMS_5: Final[str] = "165,5 × 84,8 × 65"
_DIMS_8_20: Final[str] = "180 × 100 × 68"

TORQUE_SPECS: dict[int, dict[str, str]] = {
    5: {
        "moment": "5 Нм",
        "damper-area": "до 0,5",
        "running-time": "< 10 с (90°)",
        "noise": "55",
        "dimensions": _DIMS_5,
        "weight": "0,8",
        "shaft-diameter": "○ 10…16 / □ 8×8…14×14",
        "power_24": "8 Вт (работа) / 1 Вт (удержание)",
        "power_230": "8 Вт (работа) / 1 Вт (удержание)",
        "transformer-va": "18",
    },
    8: {
        "moment": "8 Нм",
        "damper-area": "до 0,8",
        "running-time": "< 8 с (90°)",
        "noise": "65",
        "dimensions": _DIMS_8_20,
        "weight": "1,2",
        "shaft-diameter": "○ 10…20 / □ 10×10…16×16",
        "power_24": "12 Вт (работа) / 0,8 Вт (удержание)",
        "power_230": "12 Вт (работа) / 1 Вт (удержание)",
        "transformer-va": "18",
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "до 1,0",
        "running-time": "< 10 с (90°)",
        "noise": "65",
        "dimensions": _DIMS_8_20,
        "weight": "1,2",
        "shaft-diameter": "○ 10…20 / □ 10×10…14×14",
        "power_24": "12 Вт (работа) / 0,8 Вт (удержание)",
        "power_230": "12 Вт (работа) / 1 Вт (удержание)",
        "transformer-va": "25",
    },
    20: {
        "moment": "20 Нм",
        "damper-area": "до 2,0",
        "running-time": "< 20 с (90°)",
        "noise": "65",
        "dimensions": _DIMS_8_20,
        "weight": "1,2",
        "shaft-diameter": "○ 10…20 / □ 10×10…14×14",
        "power_24": "12 Вт (работа) / 0,8 Вт (удержание)",
        "power_230": "12 Вт (работа) / 1 Вт (удержание)",
        "transformer-va": "25",
    },
}

# Back-compat snapshot of 8 Нм shared rows (tests / docs).
SHARED_ATTRS: tuple[AttrRow, ...] = (
    ("Крутящий момент", "moment", "Нм", "8 Нм", ATTR_GROUP_FUNCTIONAL),
    ("Площадь заслонки", "damper-area", "м²", "до 0,8", ATTR_GROUP_FUNCTIONAL),
    (
        "Сечение клемм",
        "terminal-size",
        "мм²",
        "макс. 2,0",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Направление вращения",
        "rotation-direction",
        "",
        "задаётся вручную",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Ручное управление",
        "manual-override",
        "",
        MANUAL_OVERRIDE_BUTTON_SELF_RESET,
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Угол поворота",
        "rotation-angle",
        "°",
        "макс. 90°",
        ATTR_GROUP_FUNCTIONAL,
    ),
    ("Уровень шума", "noise", "дБ(A)", "65", ATTR_GROUP_FUNCTIONAL),
    (
        "Индикация положения",
        "position-indication",
        "",
        "механическая",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Степень защиты корпуса",
        "ip-rating",
        "",
        "IP54",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура окружающей среды",
        "ambient-temp",
        "°C",
        "–20…+50 (IEC 721-3-3)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура хранения",
        "storage-temp",
        "°C",
        "–30…+80 (IEC 721-3-2)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Относительная влажность",
        "humidity",
        "",
        "95 %, без конденсата (EN 60730-1)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Габаритные размеры",
        "dimensions",
        "мм",
        _DIMS_8_20,
        ATTR_GROUP_SIZE,
    ),
    (
        "Длина вала заслонки",
        "shaft-length",
        "мм",
        "≥ 50",
        ATTR_GROUP_SIZE,
    ),
    (
        "Диаметр вала",
        "shaft-diameter",
        "мм",
        "○ 10…20 / □ 10×10…16×16",
        ATTR_GROUP_SIZE,
    ),
    ("Масса", "weight", "кг", "1,2", ATTR_GROUP_SIZE),
    (
        "Сечение провода",
        "wire-cross-section",
        "мм²",
        "0,5",
        ATTR_GROUP_ELECTRICAL,
    ),
)

CANONICAL_SLUGS: frozenset[str] = frozenset(
    {
        *(row[1] for row in _SHARED_BASE),
        "moment",
        "damper-area",
        "running-time",
        "noise",
        "dimensions",
        "shaft-diameter",
        "weight",
        "voltage",
        "power-consumption",
        "transformer-va",
        "protection-class",
        "control",
        "aux-switch",
    },
)


def product_slug_for_nm(nm: int) -> str:
    """Product.slug for DA{n}MQU family tile."""
    return f"privod-vozdushniy-da{nm}mqu-{nm}nm"


def damqu_product_slugs() -> frozenset[str]:
    """All Product.slug values owned by the DAMQU enricher."""
    return frozenset(product_slug_for_nm(nm) for nm in TORQUE_SPECS)


def is_damqu_product_slug(slug: str | None) -> bool:
    """True when product slug is a DAMQU family tile."""
    return bool(_PRODUCT_SLUG_RE.fullmatch((slug or "").strip()))


def parse_damqu_torque_nm(sku_code: str) -> int | None:
    """Return Nm for DA..MQU codes, else None."""
    match = _SKU_RE.fullmatch((sku_code or "").strip())
    if match is None:
        return None
    nm = int(match.group("nm"))
    return nm if nm in TORQUE_SPECS else None


def damqu_product_queryset() -> QuerySet[Product]:
    """Products that host DA..MQU SKUs."""
    return Product.objects.filter(slug__iregex=_PRODUCT_SLUG_RE.pattern).distinct()


def _product_title(nm: int) -> str:
    return PRODUCT_NAME_TMPL.format(nm=nm)


def _sku_description(variant: SkuVariant, *, row: dict[str, str]) -> str:
    """PDP description: purpose + application; ТТХ stay in attribute cards."""
    lines = [
        (
            "Электропривод воздушной заслонки ускоренного срабатывания "
            "без возвратной пружины. Используется в воздушных клапанах "
            "систем ОВК."
        ),
        (
            f"Без возвратной пружины: положение заслонки фиксируется "
            f"при отключении питания. Площадь заслонки — {row['damper-area']} м²."
        ),
        "",
        "Область применения:",
        "– Общеобменная вентиляция (офисы, торговые центры).",
        ("– Спецобъекты: аэропорты, метро, ТЭЦ, медицинские учреждения, животноводческие фермы."),
        "– Центральное кондиционирование и отопление.",
    ]
    if variant.control == "modulating":
        lines.append(
            "– Управление: пропорциональное (модулирующее), сигнал 0…10 В=.",
        )
    elif variant.control == "on_off":
        lines.append("– Управление: 2-/3-позиционное.")
    if variant.aux_switch is True:
        lines.append("– Вспомогательный переключатель: 2 SPDT.")
    lines.append(f"– Крутящий момент: {row['moment']}.")
    lines.append(f"– Время поворота: {row['running-time']}.")
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    """Remove all EAV rows for this SKU before rewrite."""
    AttributeValue.objects.filter(sku=sku).delete()


def _enrich_sku(
    sku: SKU,
    *,
    row: dict[str, str],
    title: str,
    category_slug: str,
) -> int:
    """Rewrite one SKU; return attribute write count."""
    variant = parse_sku_variant(sku.sku_code)
    sku.name = title[:300]
    sku.description = _sku_description(variant, row=row)
    sku.specs_text = ""
    sku.save(update_fields=["name", "description", "specs_text"])

    _clear_sku_attributes(sku)
    attrs = 0

    family_attrs: tuple[AttrRow, ...] = (
        ("Крутящий момент", "moment", "Нм", row["moment"], ATTR_GROUP_FUNCTIONAL),
        (
            "Площадь заслонки",
            "damper-area",
            "м²",
            row["damper-area"],
            ATTR_GROUP_FUNCTIONAL,
        ),
        (
            "Время поворота",
            "running-time",
            "с",
            row["running-time"],
            ATTR_GROUP_FUNCTIONAL,
        ),
        ("Уровень шума", "noise", "дБ(A)", row["noise"], ATTR_GROUP_FUNCTIONAL),
        (
            "Габаритные размеры",
            "dimensions",
            "мм",
            row["dimensions"],
            ATTR_GROUP_SIZE,
        ),
        (
            "Диаметр вала",
            "shaft-diameter",
            "мм",
            row["shaft-diameter"],
            ATTR_GROUP_SIZE,
        ),
        ("Масса", "weight", "кг", row["weight"], ATTR_GROUP_SIZE),
    )
    for name, slug, unit, value, _group in (*family_attrs, *_SHARED_BASE):
        _set_attr(sku, name, slug, unit, value)
        attrs += 1

    if variant.voltage == "24":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC/DC 24 В, 50/60 Гц",
        )
        _set_attr(
            sku,
            "Потребляемая мощность",
            "power-consumption",
            "",
            row["power_24"],
        )
        _set_attr(
            sku,
            "Мощность трансформатора",
            "transformer-va",
            "В·А",
            row["transformer-va"],
        )
        _set_attr(
            sku,
            "Класс защиты",
            "protection-class",
            "",
            "III (безопасное сверхнизкое напряжение)",
        )
        attrs += 4
    elif variant.voltage == "230":
        _set_attr(
            sku,
            "Номинальное напряжение",
            "voltage",
            "",
            "AC 100…240 В, 50/60 Гц",
        )
        _set_attr(
            sku,
            "Потребляемая мощность",
            "power-consumption",
            "",
            row["power_230"],
        )
        _set_attr(
            sku,
            "Мощность трансформатора",
            "transformer-va",
            "В·А",
            row["transformer-va"],
        )
        _set_attr(
            sku,
            "Класс защиты",
            "protection-class",
            "",
            "II (все изолировано / полная изоляция)",
        )
        attrs += 4

    if variant.control == "modulating":
        _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
        attrs += 1
        _set_attr(
            sku,
            CONTROL_SIGNAL_Y_LABEL,
            CONTROL_SIGNAL_Y_SLUG,
            "",
            CONTROL_SIGNAL_Y_CANON,
        )
        _set_attr(
            sku,
            FEEDBACK_SIGNAL_U_LABEL,
            FEEDBACK_SIGNAL_U_SLUG,
            "",
            FEEDBACK_SIGNAL_U_CANON,
        )
        attrs += 2
    elif variant.control == "on_off":
        _set_attr(
            sku,
            "Управление",
            "control",
            "",
            normalize_control_attribute_value(
                "2-/3-позиционное",
                sku_code=sku.sku_code,
                category_slug=category_slug,
            ),
        )
        attrs += 1

    if variant.aux_switch is True:
        from catalog.facets import aux_spdt_count_from_sku, normalize_aux_switch_value

        count = aux_spdt_count_from_sku(sku.sku_code) or 2
        _set_attr(
            sku,
            "Вспомогательный переключатель",
            "aux-switch",
            "",
            normalize_aux_switch_value(f"SPDT-{count}", sku_code=sku.sku_code),
        )
        attrs += 1

    return attrs


def apply_damqu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Clear and rewrite all DA..MQU product/SKU copy and categorized ТТХ.

    Returns:
        Counters: products, skus, attributes, dry_run.
    """
    products = list(damqu_product_queryset().select_related("category").order_by("slug"))
    summary: dict[str, Any] = {
        "products": 0,
        "skus": 0,
        "attributes": 0,
        "dry_run": dry_run,
        "by_nm": {},
    }
    if not products:
        return summary

    for product in products:
        skus = list(SKU.objects.filter(product=product).order_by("sku_code"))
        if not skus:
            continue
        sample_nm = parse_damqu_torque_nm(skus[0].sku_code)
        if sample_nm is None:
            sample_nm = torque_nm_from_sku_code(skus[0].sku_code)
        if sample_nm is None or sample_nm not in TORQUE_SPECS:
            continue
        title = _product_title(sample_nm)
        category_slug = product.category.slug if product.category_id else ""

        summary["products"] += 1
        summary["by_nm"].setdefault(sample_nm, 0)

        if not dry_run:
            product.name = title[:200]
            product.description = SERIES_DESCRIPTION
            product.specs_text = ""
            product.save(update_fields=["name", "description", "specs_text"])

        for sku in skus:
            nm = parse_damqu_torque_nm(sku.sku_code) or sample_nm
            spec = TORQUE_SPECS.get(nm)
            if spec is None:
                continue
            summary["skus"] += 1
            summary["by_nm"][nm] = summary["by_nm"].get(nm, 0) + 1
            if dry_run:
                continue
            summary["attributes"] += _enrich_sku(
                sku,
                row=spec,
                title=_product_title(nm),
                category_slug=category_slug,
            )

    return summary
