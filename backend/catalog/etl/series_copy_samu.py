"""Canonical copy + ТТХ for Hoocon SA..MU (smoke damper, no spring return).

Source: English manuals ``sa{n}mu-ds_dst.pdf`` (Nm 10/15/30) + Belimo RU glossary.
SA7 shares the SA..MU manuals family; catalog SKUs include 7/10/15/30 Нм.
"""

from __future__ import annotations

import re
from typing import Any

from django.db.models import QuerySet

from catalog.etl.attr_groups import (
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant, sku_code_is_thermal
from catalog.etl.tech_copy import (
    MANUAL_SAFETY_ATTENTION_LINES,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.facets import normalize_aux_switch_value
from catalog.facets.temp_sensor import TEMP_SENSOR_NONE, TEMP_SENSOR_SAF72
from catalog.models import SKU, AttributeValue, Product

_SAMU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)mu")

AttrRow = tuple[str, str, str, str, str]

SHARED_ATTRS: tuple[AttrRow, ...] = (
    (
        "Направление вращения",
        "rotation-direction",
        "",
        "для монтажа с противоположной стороны",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Ручное управление",
        "manual-override",
        "",
        "металлическая рукоятка",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Угол поворота",
        "rotation-angle",
        "°",
        "макс. 95°",
        ATTR_GROUP_FUNCTIONAL,
    ),
    (
        "Индикация положения",
        "position-indication",
        "",
        "механический указатель",
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
        "–30…+50 °C",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура хранения",
        "storage-temp",
        "°C",
        "–30…+80 °C",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Относительная влажность",
        "humidity",
        "",
        "95 %, без конденсации (EN 60730-1)",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Диаметр вала",
        "shaft-diameter",
        "мм",
        "квадратный 12×12 мм",
        ATTR_GROUP_SIZE,
    ),
)

# Per-Nm family: dimensions shared by all SKUs of that family; weight may differ by Nm.
_SAMU_DIMENSIONS_SEE_DRAWING = "см. «Габаритные размеры»"

TORQUE_SPECS: dict[int, dict[str, str]] = {
    7: {
        "moment": "7 Нм",
        "damper-area": "до 0,7 м²",
        "running-time": "< 45 с (95°)",
        "shaft-length": "≥ 50",
        "weight": "≈ 1,7 кг",
        "dimensions": _SAMU_DIMENSIONS_SEE_DRAWING,
        "power_24": "5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "5 Вт (работа) / 1 Вт (удержание)",
        "noise": "макс. 50 дБ(А)",
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "running-time": "< 45 с (95°)",
        "shaft-length": "≥ 50",
        "weight": "≈ 1,7 кг",
        "dimensions": _SAMU_DIMENSIONS_SEE_DRAWING,
        "power_24": "5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "5 Вт (работа) / 1 Вт (удержание)",
        "noise": "макс. 50 дБ(А)",
    },
    15: {
        "moment": "15 Нм",
        "damper-area": "до 1,5 м²",
        "running-time": "< 30 с (95°)",
        "shaft-length": "≥ 50",
        "weight": "≈ 1,7 кг",
        "dimensions": _SAMU_DIMENSIONS_SEE_DRAWING,
        "power_24": "7 Вт (работа) / 1,5 Вт (удержание)",
        "power_230": "7 Вт (работа) / 1,5 Вт (удержание)",
        "noise": "макс. 50 дБ(А)",
    },
    30: {
        "moment": "30 Нм",
        "damper-area": "до 3,0 м²",
        "running-time": "< 115 с (95°)",
        "shaft-length": "≥ 90",
        "weight": "≈ 2,2 кг",
        "dimensions": _SAMU_DIMENSIONS_SEE_DRAWING,
        "power_24": "10 Вт (работа) / 2 Вт (удержание)",
        "power_230": "10 Вт (работа) / 2 Вт (удержание)",
        "noise": "макс. 45 дБ(А)",
    },
}

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод дымового клапана без возвратной пружины.
Используется в системах дымоудаления и противодымной вентиляции.

Назначение и особенности серии SA..MU:
– Управление: открыто/закрыто, 2-/3-позиционное.
– Вспомогательные переключатели: 2 SPDT (исполнения -DS / -DST).
– Исполнение -DST: термодатчик SAF72 (окружающая среда TS1 и канал TS2, 72 °C).
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –30…+50 °C.
""".strip(),
)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Инструкция по установке и управлению приводом дымового клапана Hoocon SA..MU",
            (
                "Для корректной работы приводов серии SA..MU соблюдайте рекомендации "
                "по монтажу, подключению и настройке."
            ),
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
            "",
            "1. Подготовка к установке",
            "",
            "– Длина вала — см. таблицу характеристик выбранного артикула (≥ 50 или ≥ 90 мм).",
            "– Диаметр вала: квадратный 12×12 мм.",
            "",
            "2. Монтаж привода",
            "",
            "– Закрепите привод на валу; ручное управление — металлическая рукоятка.",
            "– Угол поворота: макс. 95°.",
            "",
            "3. Электрическое подключение",
            "",
            "– Исполнения 24 В: AC/DC 24 В (класс III).",
            "– Исполнения 230 В: AC 100…240 В (класс II).",
            "– Сечение провода: 0,5 мм².",
            "– Схемы — в галерее и PDF инструкции.",
            "",
            "4. Вспомогательные переключатели (-DS / -DST)",
            "",
            "– 2 группы SPDT; настройте угол срабатывания по таблице в инструкции.",
            "– Исполнение -DST: термодатчик — см. комплектность артикула.",
        ],
    ),
)


def parse_samu_torque_nm(sku_code: str) -> int | None:
    """Extract torque from ``SA10MU24-DS`` → ``10``."""
    match = _SAMU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def instructions_for_samu_sku(sku_code: str) -> str | None:
    """Build install guide scoped to one SA..MU edition."""
    from catalog.etl.sku_instructions import format_damper_area, power_supply_bullets

    torque_nm = parse_samu_torque_nm(sku_code)
    if torque_nm is None:
        return None
    row = TORQUE_SPECS.get(torque_nm)
    if row is None:
        return None
    variant = parse_sku_variant(sku_code)
    thermal = sku_code_is_thermal(sku_code)
    series = f"SA{torque_nm}MU"
    shaft_len = row["shaft-length"]
    if "мм" not in shaft_len:
        shaft_len = f"{shaft_len} мм"
    lines: list[str] = [
        f"Инструкция по установке и управлению приводом дымового клапана Hoocon {series}",
        (f"Для корректной работы привода {series} соблюдайте рекомендации по монтажу, подключению и настройке."),
        "",
        *MANUAL_SAFETY_ATTENTION_LINES,
        "",
        "1. Подготовка к установке",
        "",
        f"– Длина вала заслонки: {shaft_len}.",
        "– Диаметр вала: квадратный 12×12 мм.",
        (f"– Крутящий момент: {row['moment']}; площадь заслонки {format_damper_area(row['damper-area'])}."),
        f"– Габаритные размеры: {row['dimensions']}.",
        "",
        "2. Монтаж привода",
        "",
        "– Закрепите привод на валу; ручное управление — металлическая рукоятка.",
        "– Угол поворота: макс. 95°.",
        "",
        "3. Электрическое подключение",
        "",
        *power_supply_bullets(variant),
        "– Сечение провода: 0,5 мм².",
        "– Схемы — в галерее и PDF инструкции.",
    ]
    next_ch = 4
    if variant.aux_switch is True:
        lines.extend(
            [
                "",
                f"{next_ch}. Вспомогательные переключатели",
                "",
                "– 2 группы SPDT; настройте угол срабатывания по таблице в инструкции.",
            ],
        )
        next_ch += 1
    if thermal:
        lines.extend(
            [
                "",
                f"{next_ch}. Термодатчик",
                "",
                "– Исполнение с термодатчиком — см. комплектность артикула и PDF инструкции.",
            ],
        )
    return normalize_tech_copy("\n".join(lines))


def is_samu_sku(sku_code: str) -> bool:
    """True for SA..MU smoke editions."""
    return parse_samu_torque_nm(sku_code) is not None


def samu_product_queryset() -> QuerySet[Product]:
    """Products that own at least one SA..MU SKU."""
    return Product.objects.filter(skus__sku_code__iregex=r"(?i)^sa\d+mu").distinct()


def _product_title(torque_nm: int) -> str:
    return f"SA{torque_nm}MU | Электропривод дымового клапана без возвратной пружины, {torque_nm} Нм"


def _sku_description(variant: SkuVariant, row: dict[str, str]) -> str:
    from catalog.etl.sku_instructions import format_damper_area

    lines = [
        (
            "Электропривод дымового клапана без возвратной пружины. "
            f"Крутящий момент {row['moment']}, площадь заслонки {format_damper_area(row['damper-area'])}."
        ),
        f"Время поворота: {row['running-time']}.",
        "Управление: открыто/закрыто, 2-/3-позиционное.",
        "Вспомогательные переключатели: 2 SPDT.",
    ]
    if sku_code_is_thermal(variant.code):
        lines.append(
            "Термодатчик: SAF72 (TS1 — окружающая среда, TS2 — канал, срабатывание при 72 °C).",
        )
    else:
        lines.append("Термодатчик: без датчика (исполнение -DS).")
    if variant.voltage == "24":
        lines.append("Номинальное напряжение: AC/DC 24 В, 50/60 Гц.")
    elif variant.voltage == "230":
        lines.append("Номинальное напряжение: AC 100…240 В, 50/60 Гц.")
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    AttributeValue.objects.filter(sku=sku).delete()


def apply_samu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite SA..MU products/SKUs from English smoke-damper manuals."""
    products = list(samu_product_queryset().select_related("category"))
    skus_done = 0
    attrs = 0
    for product in products:
        skus = [s for s in SKU.objects.filter(product=product) if is_samu_sku(s.sku_code)]
        torque_nm = None
        for sku in skus:
            torque_nm = parse_samu_torque_nm(sku.sku_code)
            if torque_nm is not None:
                break
        if torque_nm is None or torque_nm not in TORQUE_SPECS:
            continue
        title = _product_title(torque_nm)
        if not dry_run:
            product.name = title[:300]
            product.description = SERIES_DESCRIPTION
            product.instructions = SERIES_INSTRUCTIONS
            product.specs_text = ""
            product.save(
                update_fields=["name", "description", "instructions", "specs_text"],
            )

        for sku in skus:
            nm = parse_samu_torque_nm(sku.sku_code) or torque_nm
            row = TORQUE_SPECS.get(nm)
            if row is None:
                continue
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                sku.name = _product_title(nm)[:300]
                sku.description = _sku_description(variant, row)
                sku.specs_text = ""
                sku.save(update_fields=["name", "description", "specs_text"])
                _clear_sku_attributes(sku)

            for name, slug, unit, value, _g in SHARED_ATTRS:
                if not dry_run:
                    _set_attr(sku, name, slug, unit, value)
                attrs += 1

            for name, slug, unit, value in (
                ("Крутящий момент", "moment", "Нм", row["moment"]),
                ("Площадь заслонки", "damper-area", "м²", row["damper-area"]),
                ("Время поворота", "running-time", "с", row["running-time"]),
                ("Уровень шума", "noise", "дБ(A)", row["noise"]),
                ("Длина вала заслонки", "shaft-length", "мм", row["shaft-length"]),
                ("Масса", "weight", "кг", row["weight"]),
                ("Габаритные размеры", "dimensions", "мм", row["dimensions"]),
            ):
                if not dry_run:
                    _set_attr(sku, name, slug, unit, value)
                attrs += 1

            if variant.voltage == "24":
                if not dry_run:
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
                        "Класс защиты",
                        "protection-class",
                        "",
                        "III (безопасное сверхнизкое напряжение)",
                    )
                attrs += 3
            elif variant.voltage == "230":
                if not dry_run:
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
                        "Класс защиты",
                        "protection-class",
                        "",
                        "II (все изолировано / полная изоляция)",
                    )
                attrs += 3

            if not dry_run:
                _set_attr(
                    sku,
                    "Управление",
                    "control",
                    "",
                    normalize_control_attribute_value("2-/3-позиционное"),
                )
                _set_attr(
                    sku,
                    "Вспомогательный переключатель",
                    "aux-switch",
                    "",
                    normalize_aux_switch_value("SPDT-2", sku_code=sku.sku_code),
                )
                temp_value = TEMP_SENSOR_SAF72 if sku_code_is_thermal(sku.sku_code) else TEMP_SENSOR_NONE
                _set_attr(sku, "Датчик температуры", "temp-sensor", "", temp_value)
            attrs += 3
            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "dry_run": dry_run,
    }
