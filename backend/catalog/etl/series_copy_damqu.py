"""Canonical copy + ТТХ for Hoocon DA..MQU (fast damper, no spring return).

Source: product datasheet, Belimo RU glossary (docs/tech-copy-belimo-ru.md).
Characteristics are stored as EAV rows with group keys for PDP cards.
"""

from __future__ import annotations

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import SKU, AttributeValue, Product

PRODUCT_SLUG = "privod-vozdushniy-da8mqu-8nm"

PRODUCT_NAME = "DA8MQU | Электропривод воздушный ускоренного срабатывания без возвратной пружины"

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
– Время поворота: 5…20 с (90°), зависит от модели.
– Крутящий момент: 5…20 Нм (DA5MQU, DA8MQU, DA16MQU, DA20MQU).
– Потребление: 0,8…1,0 Вт в режиме удержания, 8…12 Вт при работе.
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –20…+50 °C.

DA8MQU:
– Крутящий момент: 8 Нм.
– Площадь обслуживаемой заслонки: до 0,8 м².
– Габаритные размеры (Д × Ш × В): 180 × 100 × 68 мм.
– Масса: 1,2 кг.

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

# name, slug, unit, value, group_key
AttrRow = tuple[str, str, str, str, str]

SHARED_ATTRS: tuple[AttrRow, ...] = (
    # Functional
    ("Крутящий момент", "moment", "Нм", "8 Нм", ATTR_GROUP_FUNCTIONAL),
    (
        "Площадь заслонки",
        "damper-area",
        "м²",
        "до 0,8",
        ATTR_GROUP_FUNCTIONAL,
    ),
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
        "кнопка с самовозвратом редуктора",
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
    # Operating (shared IP / humidity / temps; class is edition-specific)
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
    # Size
    (
        "Габаритные размеры",
        "dimensions",
        "мм",
        "180 × 100 × 68",
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
    # Electrical shared
    (
        "Сечение провода",
        "wire-cross-section",
        "мм²",
        "0,5",
        ATTR_GROUP_ELECTRICAL,
    ),
)

# Slugs owned by this enricher (documentation; wipe is full SKU clear).
CANONICAL_SLUGS: frozenset[str] = frozenset(
    {
        *(row[1] for row in SHARED_ATTRS),
        "voltage",
        "power-consumption",
        "transformer-va",
        "protection-class",
        "control",
        "aux-switch",
    },
)


def _sku_description(variant: SkuVariant) -> str:
    """PDP description: purpose + application; ТТХ stay in attribute cards."""
    lines = [
        (
            "Электропривод воздушной заслонки ускоренного срабатывания "
            "без возвратной пружины. Используется в воздушных клапанах "
            "систем ОВК."
        ),
        (
            "Без возвратной пружины: положение заслонки фиксируется "
            "при отключении питания. Площадь заслонки — до 0,8 м²."
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
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    """Remove all EAV rows for this SKU before rewrite."""
    AttributeValue.objects.filter(sku=sku).delete()


def apply_damqu_enrichment() -> dict[str, int]:
    """Clear and rewrite DA8MQU product/SKU copy and categorized ТТХ.

    Returns:
        Counters: products, skus, attributes_touched.
    """
    product = Product.objects.filter(slug=PRODUCT_SLUG).select_related("category").first()
    if product is None:
        return {"products": 0, "skus": 0, "attributes": 0}

    product.name = PRODUCT_NAME[:300]
    product.description = SERIES_DESCRIPTION
    product.specs_text = ""  # cards only — no prose duplicate
    product.save(update_fields=["name", "description", "specs_text"])

    category_slug = product.category.slug if product.category_id else ""
    skus = list(SKU.objects.filter(product=product))
    attrs = 0
    for sku in skus:
        variant = parse_sku_variant(sku.sku_code)
        sku.name = PRODUCT_NAME[:300]
        sku.description = _sku_description(variant)
        sku.specs_text = ""
        sku.save(update_fields=["name", "description", "specs_text"])

        _clear_sku_attributes(sku)

        for name, slug, unit, value, _group in SHARED_ATTRS:
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
                "12 Вт (работа) / 0,8 Вт (удержание)",
            )
            _set_attr(
                sku,
                "Мощность трансформатора",
                "transformer-va",
                "В·А",
                "18",
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
                "12 Вт (работа) / 1 Вт (удержание)",
            )
            _set_attr(
                sku,
                "Класс защиты",
                "protection-class",
                "",
                "II (все изолировано / полная изоляция)",
            )
            attrs += 3

        if variant.control == "modulating":
            from catalog.etl.tech_copy import CONTROL_MODULATING

            _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
        elif variant.control == "on_off":
            from catalog.etl.tech_copy import normalize_control_attribute_value

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
        # Absent → do not write «Нет» (omit the attribute entirely).

    return {"products": 1, "skus": len(skus), "attributes": attrs}
