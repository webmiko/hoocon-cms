"""Canonical copy + ТТХ for Hoocon HVD-…F (smoke damper, spring return).

Source: English manuals ``hvd-{3,5}f-s_st.pdf`` + Belimo RU glossary.
Card structure mirrors SA..MU (one product per Nm, four editions);
physics matches SA..FU (spring return, SAF72 on ST).
"""

from __future__ import annotations

import re
from typing import Any

from django.db.models import QuerySet

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_instructions import damper_area_for_nm
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant, sku_code_is_thermal
from catalog.etl.tech_copy import (
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    MANUAL_SAFETY_ATTENTION_LINES,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.facets import normalize_aux_switch_value
from catalog.models import SKU, AttributeValue, Category, Product

# HVD24S-3F / HVD24ST-3F / HVD230S-5F …
_HVDF_CODE = re.compile(
    r"(?i)^hvd(?P<volt>24|230)(?P<aux>s(?:t)?)-(?P<nm>\d+)f$",
)

AttrRow = tuple[str, str, str, str, str]

CATEGORY_SLUG = "elektroprivody-dlya-klapanov-dymoudaleniya"

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
        MANUAL_OVERRIDE_BUTTON_SELF_RESET,
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
        "–20…+50 °C",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Температура хранения",
        "storage-temp",
        "°C",
        "–40…+70 °C",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Относительная влажность",
        "humidity",
        "",
        "95 % относительной влажности, без конденсации",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Диаметр вала",
        "shaft-diameter",
        "мм",
        "квадратный 12×12 мм (втулки 8×8, 10×10 мм)",
        ATTR_GROUP_SIZE,
    ),
    (
        "Сечение провода",
        "wire-cross-section",
        "мм²",
        "0,5 мм²",
        ATTR_GROUP_ELECTRICAL,
    ),
)

_TorqueSpec = dict[str, str]
_HVDF_3_DIMENSIONS = "132 × 88 × 59 мм"
_HVDF_5_DIMENSIONS = "158 × 102 × 59 мм"

TORQUE_SPECS: dict[int, _TorqueSpec] = {
    3: {
        "moment": "3 Нм",
        "damper-area": damper_area_for_nm(3),
        "power": "5 Вт под нагрузкой / 2 Вт в режиме удержания",
        "running-time": "< 75 с / возврат пружины < 25 с",
        "weight": "< 1,3 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "> 50 мм",
        "dimensions": _HVDF_3_DIMENSIONS,
    },
    5: {
        "moment": "5 Нм",
        "damper-area": damper_area_for_nm(5),
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "< 70 с / возврат пружины < 20 с",
        "weight": "< 1,5 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _HVDF_5_DIMENSIONS,
    },
}

TEMP_SENSOR_NONE = "Нет"
TEMP_SENSOR_SAF72 = "SAF72"

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод дымового клапана с пружинным возвратом.
Специально разработан для малогабаритных и средних оконечных воздушных
заслонок и узлов управления системой воздушного потока. Благодаря малым
габаритам и гибкости управления применяется в местах с ограниченным пространством.

Особенности серии HVD-…F:
– Пружинный возврат при отключении питания.
– Управление: открыто/закрыто.
– Две группы вспомогательных переключателей (исполнение S / ST).
– Ручное управление: кнопка с самовозвратом (редуктор выводится из зацепления).
– Угол поворота: макс. 95°.
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –20…+50 °C.
– Температура хранения: –40…+70 °C.
– Исполнение ST: термодатчик SAF72 (окружающая среда TS1 и канал TS2, 72 °C).
""".strip(),
)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Инструкция по установке и управлению приводом дымового клапана Hoocon HVD-…F",
            (
                "Для корректной работы приводов серии HVD-…F соблюдайте рекомендации "
                "по монтажу, подключению и настройке."
            ),
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
            "",
            "1. Подготовка к установке",
            "",
            "– Длина вала — см. таблицу характеристик выбранного артикула "
            "(> 50 мм для HVD-3F или < 90 мм для HVD-5F).",
            "– Диаметр вала: квадратный 12×12 мм (втулки 8×8 и 10×10 мм).",
            "",
            "2. Монтаж привода",
            "",
            "– Закрепите привод на валу; направление вращения — монтаж с противоположной стороны.",
            "– Угол поворота: макс. 95°.",
            (
                "– Ручное управление: редуктор выводится из зацепления при помощи кнопки "
                "с самовозвратом, ручная блокировка."
            ),
            "",
            "3. Электрическое подключение",
            "",
            "– Исполнения 24 В: AC/DC 24 В, 50/60 Гц (класс защиты III).",
            "– Исполнения 230 В: AC 100…240 В, 50/60 Гц (класс защиты II).",
            "– Сечение провода: 0,5 мм².",
            "– Схемы — в галерее и PDF инструкции.",
            "",
            "4. Вспомогательные переключатели (S / ST)",
            "",
            "– Две группы SPDT (S1–S3 и S4–S6); настройте угол срабатывания по таблице в инструкции.",
            "– Исполнение ST: термодатчик SAF72 — TS1 (окружающая среда) и TS2 (канал), 72 °C.",
            "",
            "5. Аварийный возврат пружиной",
            "",
            (
                "– При отключении питания пружина возвращает клапан в исходное положение "
                "(время поворота двигателя и возврата пружины — см. характеристики артикула)."
            ),
        ],
    ),
)

# Belimo BFL ≈ 4/3 Нм (HVD-3F); BLF ≈ 6/4 Нм (HVD-5F). ST ↔ Belimo …-T (BAT 72 °C).
_ANALOGS_BY_NM: dict[int, str] = {
    3: normalize_tech_copy(
        """
Список аналогов электропривода Hoocon HVD-3F с такими же или близкими характеристиками
(пружинный возврат, открыто/закрыто, ~3 Нм, 2×SPDT, IP54, вал 12×12 мм)

HVD24S-3F:
– Belimo BFL24
– BVM BFL24-03
– Nanotek BFL 24 B

HVD24ST-3F: (с термодатчиком)
– Belimo BFL24-T
– BVM BFL24-03-T
– Nanotek BFL 24 B-T

HVD230S-3F:
– Belimo BFL230
– BVM BFL230-03
– Nanotek BFL 230 B

HVD230ST-3F: (с термодатчиком)
– Belimo BFL230-T
– BVM BFL230-03-T
– Nanotek BFL 230 B-T
""".strip(),
    ),
    5: normalize_tech_copy(
        """
Список аналогов электропривода Hoocon HVD-5F с такими же или близкими характеристиками
(пружинный возврат, открыто/закрыто, ~5 Нм, 2×SPDT, IP54, вал 12×12 мм)

HVD24S-5F:
– Belimo BLF24
– Nanotek BLF 24 B
– Sputnik FS24-5
– BVM BLF24-05
– Vilmann TAFA2-05S24

HVD24ST-5F: (с термодатчиком)
– Belimo BLF24-T
– Nanotek BLF 24 B-T
– Sputnik FS24-5-ST
– BVM BLF24-05-T
– Vilmann TAFA2-05ST24

HVD230S-5F:
– Belimo BLF230
– Nanotek BLF 230 B
– Sputnik FS230-5
– BVM BLF230-05
– AIRS BLF230A

HVD230ST-5F: (с термодатчиком)
– Belimo BLF230-T
– Nanotek BLF 230 B-T
– Sputnik FS230-5-ST
– BVM BLF230-05-T
– AIRS BLF230A-T
""".strip(),
    ),
}

# (voltage, thermal) → sku_code suffix pattern already full code
_EDITIONS: tuple[tuple[str, bool], ...] = (
    ("24", False),
    ("24", True),
    ("230", False),
    ("230", True),
)


def parse_hvdf_torque_nm(sku_code: str) -> int | None:
    """Extract torque from ``HVD24ST-3F`` → ``3``."""
    match = _HVDF_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def instructions_for_hvdf_sku(sku_code: str) -> str | None:
    """Build install guide scoped to one HVD-…F edition."""
    from catalog.etl.sku_instructions import format_damper_area, power_supply_bullets

    torque_nm = parse_hvdf_torque_nm(sku_code)
    if torque_nm is None:
        return None
    row = TORQUE_SPECS.get(torque_nm)
    if row is None:
        return None
    variant = parse_sku_variant(sku_code)
    thermal = sku_code_is_thermal(sku_code)
    series = f"HVD-{torque_nm}F"
    lines: list[str] = [
        f"Инструкция по установке и управлению приводом дымового клапана Hoocon {series}",
        (f"Для корректной работы привода {series} соблюдайте рекомендации по монтажу, подключению и настройке."),
        "",
        *MANUAL_SAFETY_ATTENTION_LINES,
        "",
        "1. Подготовка к установке",
        "",
        f"– Длина вала заслонки: {row['shaft-length']}.",
        "– Диаметр вала: квадратный 12×12 мм (втулки 8×8 и 10×10 мм).",
        (f"– Крутящий момент: {row['moment']}; площадь заслонки {format_damper_area(row['damper-area'])}."),
        f"– Габаритные размеры: {row['dimensions']}.",
        "",
        "2. Монтаж привода",
        "",
        "– Закрепите привод на валу; направление вращения — монтаж с противоположной стороны.",
        "– Угол поворота: макс. 95°.",
        (
            "– Ручное управление: редуктор выводится из зацепления при помощи кнопки "
            "с самовозвратом, ручная блокировка."
        ),
        "",
        "3. Электрическое подключение",
        "",
        *power_supply_bullets(variant),
        "– Сечение провода: 0,5 мм².",
        "– Схемы — в галерее и PDF инструкции.",
        "",
        "4. Вспомогательные переключатели",
        "",
        ("– Две группы SPDT (S1–S3 и S4–S6); настройте угол срабатывания по таблице в инструкции."),
    ]
    next_ch = 5
    if thermal:
        lines.extend(
            [
                "",
                f"{next_ch}. Термодатчик SAF72",
                "",
                "– TS1 (окружающая среда) и TS2 (канал), срабатывание при 72 °C.",
            ],
        )
        next_ch += 1
    lines.extend(
        [
            "",
            f"{next_ch}. Аварийный возврат пружиной",
            "",
            (f"– При отключении питания пружина возвращает клапан в исходное положение ({row['running-time']})."),
        ],
    )
    return normalize_tech_copy("\n".join(lines))


def is_hvdf_sku(sku_code: str) -> bool:
    """True for HVD-…F spring-return smoke editions."""
    return parse_hvdf_torque_nm(sku_code) is not None


def hvdf_sku_code(*, voltage: str, thermal: bool, torque_nm: int) -> str:
    """Build catalog article ``HVD24S-3F`` / ``HVD230ST-5F``."""
    aux = "ST" if thermal else "S"
    return f"HVD{voltage}{aux}-{torque_nm}F"


def product_slug_for_nm(torque_nm: int) -> str:
    """Stable product slug for one HVD-…F torque family."""
    return f"privod-dimoudaleniya-hvd-{torque_nm}f"


def sku_slug_for(code: str, torque_nm: int) -> str:
    """Stable SKU URL segment under the product."""
    return f"{product_slug_for_nm(torque_nm)}-{code.lower()}"


def hvdf_product_queryset() -> QuerySet[Product]:
    """Products that own at least one HVD-…F SKU."""
    return Product.objects.filter(
        skus__sku_code__iregex=r"(?i)^hvd(24|230)st?-\d+f$",
    ).distinct()


def _product_title(torque_nm: int) -> str:
    return f"HVD-{torque_nm}F | Электропривод дымового клапана с пружинным возвратом, {torque_nm} Нм"


def _sku_description(variant: SkuVariant, row: _TorqueSpec) -> str:
    lines = [
        (
            "Электропривод дымового клапана с пружинным возвратом. "
            f"Крутящий момент {row['moment']}, площадь заслонки {row['damper-area']}."
        ),
        f"Время поворота: {row['running-time']}.",
        "Управление: открыто/закрыто.",
        "Вспомогательные переключатели: 2 SPDT (исполнение S / ST).",
    ]
    if sku_code_is_thermal(variant.code):
        lines.append(
            "Термодатчик: SAF72 (TS1 — окружающая среда, TS2 — канал, срабатывание при 72 °C).",
        )
    else:
        lines.append("Термодатчик: без датчика (исполнение S).")
    if variant.voltage == "24":
        lines.append("Номинальное напряжение: AC/DC 24 В, 50/60 Гц.")
    elif variant.voltage == "230":
        lines.append("Номинальное напряжение: AC 100…240 В, 50/60 Гц.")
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    AttributeValue.objects.filter(sku=sku).delete()


def ensure_hvdf_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """Create missing HVD-3F / HVD-5F products and four edition SKUs each.

    Returns:
        Counters: products_created, skus_created, dry_run.
    """
    category = Category.objects.filter(slug=CATEGORY_SLUG).first()
    if category is None:
        return {
            "products_created": 0,
            "skus_created": 0,
            "dry_run": dry_run,
            "error": f"category missing: {CATEGORY_SLUG}",
        }

    products_created = 0
    skus_created = 0
    for torque_nm in sorted(TORQUE_SPECS):
        p_slug = product_slug_for_nm(torque_nm)
        title = _product_title(torque_nm)
        product = Product.objects.filter(slug=p_slug).first()
        if product is None:
            if dry_run:
                products_created += 1
            else:
                product = Product.objects.create(
                    category=category,
                    name=title[:200],
                    slug=p_slug,
                    description=SERIES_DESCRIPTION,
                    instructions=SERIES_INSTRUCTIONS,
                )
                products_created += 1
        assert product is not None or dry_run

        for voltage, thermal in _EDITIONS:
            code = hvdf_sku_code(voltage=voltage, thermal=thermal, torque_nm=torque_nm)
            if SKU.objects.filter(sku_code__iexact=code).exists():
                continue
            if dry_run:
                skus_created += 1
                continue
            if product is None:
                continue
            SKU.objects.create(
                product=product,
                name=title[:300],
                slug=sku_slug_for(code, torque_nm),
                sku_code=code,
                description="",
                is_published=True,
            )
            skus_created += 1

    return {
        "products_created": products_created,
        "skus_created": skus_created,
        "dry_run": dry_run,
    }


def apply_hvdf_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite HVD-…F products/SKUs from English fire/smoke manuals."""
    ensure = ensure_hvdf_catalog(dry_run=dry_run)
    products = list(hvdf_product_queryset().select_related("category"))
    skus_done = 0
    attrs = 0
    for product in products:
        skus = [s for s in SKU.objects.filter(product=product) if is_hvdf_sku(s.sku_code)]
        torque_nm = None
        for sku in skus:
            torque_nm = parse_hvdf_torque_nm(sku.sku_code)
            if torque_nm is not None:
                break
        if torque_nm is None or torque_nm not in TORQUE_SPECS:
            continue
        row = TORQUE_SPECS[torque_nm]
        title = _product_title(torque_nm)
        analogs = _ANALOGS_BY_NM.get(torque_nm, "")
        if not dry_run:
            product.name = title[:200]
            product.description = SERIES_DESCRIPTION
            product.instructions = SERIES_INSTRUCTIONS
            product.specs_text = ""
            product.analogs_text = analogs
            product.save(
                update_fields=[
                    "name",
                    "description",
                    "instructions",
                    "specs_text",
                    "analogs_text",
                ],
            )

        category_slug = product.category.slug if product.category_id else ""
        for sku in skus:
            nm = parse_hvdf_torque_nm(sku.sku_code) or torque_nm
            spec = TORQUE_SPECS.get(nm, row)
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                sku.name = title[:300]
                sku.description = _sku_description(variant, spec)
                sku.specs_text = ""
                sku.analogs_text = analogs
                sku.save(
                    update_fields=["name", "description", "specs_text", "analogs_text"],
                )
                _clear_sku_attributes(sku)

            for name, slug, unit, value, _g in SHARED_ATTRS:
                if not dry_run:
                    _set_attr(sku, name, slug, unit, value)
                attrs += 1

            for name, slug, unit, value in (
                ("Крутящий момент", "moment", "Нм", spec["moment"]),
                ("Площадь заслонки", "damper-area", "м²", spec["damper-area"]),
                ("Время поворота", "running-time", "с", spec["running-time"]),
                ("Уровень шума", "noise", "дБ(A)", spec["noise"]),
                ("Длина вала заслонки", "shaft-length", "мм", spec["shaft-length"]),
                ("Масса", "weight", "кг", spec["weight"]),
                ("Габаритные размеры", "dimensions", "мм", spec["dimensions"]),
                ("Потребляемая мощность", "power-consumption", "", spec["power"]),
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
                        "Класс защиты",
                        "protection-class",
                        "",
                        "III (безопасное сверхнизкое напряжение)",
                    )
                attrs += 2
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
                        "Класс защиты",
                        "protection-class",
                        "",
                        "II (все изолировано / полная изоляция)",
                    )
                attrs += 2

            if not dry_run:
                _set_attr(
                    sku,
                    "Управление",
                    "control",
                    "",
                    normalize_control_attribute_value(
                        "открыто/закрыто",
                        sku_code=sku.sku_code,
                        category_slug=category_slug,
                    ),
                )
                _set_attr(
                    sku,
                    "Вспомогательный переключатель",
                    "aux-switch",
                    "",
                    normalize_aux_switch_value("SPDT-2", sku_code=sku.sku_code),
                )
            attrs += 2

            temp_value = TEMP_SENSOR_SAF72 if sku_code_is_thermal(sku.sku_code) else TEMP_SENSOR_NONE
            if not dry_run:
                _set_attr(sku, "Датчик температуры", "temp-sensor", "", temp_value)
            attrs += 1
            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "ensure": ensure,
        "dry_run": dry_run,
    }
