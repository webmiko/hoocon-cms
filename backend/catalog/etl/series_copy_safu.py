"""Canonical copy + ТТХ for Hoocon SA..FU (fire/smoke damper actuators).

Source of truth: English manuals ``sa{n}fu-ds_dst.pdf`` (Nm 3/5/10/15) +
Belimo RU glossary (``docs/tech-copy-belimo-ru.md``). SA20 reuses SA15
electrical/timing rows until a dedicated PDF is available; damper area is 2 м².
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
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant, sku_code_is_thermal
from catalog.etl.tech_copy import (
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    MANUAL_SAFETY_ATTENTION_LINES,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.facets import normalize_aux_switch_value
from catalog.models import SKU, AttributeValue, Product

_SAFU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fu")
_SAFU_PRODUCT = re.compile(r"(?i)protivopozharn")

AttrRow = tuple[str, str, str, str, str]

# Shared across SA..FU DS/DST (manual table + Belimo RU glossary).
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
_SAFU_SMALL_DIMENSIONS = "132 × 87 × 59 мм"
_SAFU_DIMENSIONS_SEE_DRAWING = "см. «Габаритные размеры»"

# Per-Nm rows from manuals; SA20 borrows SA15 timing/power until PDF exists.
TORQUE_SPECS: dict[int, _TorqueSpec] = {
    3: {
        "moment": "3 Нм",
        "damper-area": "< 0,3 м²",
        "power": "5 Вт под нагрузкой / 2 Вт в режиме удержания",
        "running-time": "< 75 с / возврат пружины < 25 с",
        "weight": "< 1,3 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 50 дБ(А) при возврате пружины"),
        "shaft-length": "> 50 мм",
        "dimensions": _SAFU_SMALL_DIMENSIONS,
    },
    5: {
        "moment": "5 Нм",
        "damper-area": "< 0,5 м²",
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "< 70 с / возврат пружины < 20 с",
        "weight": "< 1,5 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _SAFU_DIMENSIONS_SEE_DRAWING,
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "< 1,0 м²",
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "< 100 с / возврат пружины < 25 с",
        "weight": "< 2,5 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _SAFU_DIMENSIONS_SEE_DRAWING,
    },
    15: {
        "moment": "15 Нм",
        "damper-area": "< 1,5 м²",
        "power": "10 Вт под нагрузкой / 3,5 Вт в режиме удержания",
        "running-time": "< 150 с / возврат пружины < 25 с",
        "weight": "< 2,8 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _SAFU_DIMENSIONS_SEE_DRAWING,
    },
    20: {
        "moment": "20 Нм",
        "damper-area": "< 2,0 м²",
        "power": "10 Вт под нагрузкой / 3,5 Вт в режиме удержания",
        "running-time": "< 150 с / возврат пружины < 25 с",
        "weight": "< 2,8 кг",
        "noise": ("макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _SAFU_DIMENSIONS_SEE_DRAWING,
    },
}

TEMP_SENSOR_NONE = "Без датчика"
TEMP_SENSOR_SAF72 = "SAF72 (срабатывание при 72 °C, TS1/TS2)"

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод противопожарного / дымового клапана с пружинным возвратом.
Специально разработан для малогабаритных и средних оконечных воздушных
заслонок и узлов управления системой воздушного потока. Благодаря малым
габаритам и гибкости управления применяется в местах с ограниченным пространством.

Особенности серии SA..FU:
– Пружинный возврат при отключении питания.
– Управление: открыто/закрыто (исполнения -DS / -DST).
– Две группы вспомогательных переключателей (исполнение S).
– Ручное управление: кнопка с самовозвратом (редуктор выводится из зацепления).
– Угол поворота: макс. 95°.
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –20…+50 °C.
– Температура хранения: –40…+70 °C.
– Исполнение -DST: термодатчик SAF72 (окружающая среда TS1 и канал TS2, 72 °C).
""".strip(),
)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Инструкция по установке и управлению приводом противопожарного клапана Hoocon SA..FU",
            (
                "Для корректной работы приводов серии SA..FU важно соблюдать рекомендации "
                "по монтажу, подключению и настройке. Ниже приведены ключевые этапы и особенности."
            ),
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
            "",
            "1. Подготовка к установке",
            "",
            "Проверка совместимости:",
            "– Убедитесь, что вал заслонки соответствует требованиям артикула:",
            "– Длина вала: > 50 мм (SA3FU) или < 90 мм (SA5FU и выше) — см. характеристики.",
            "– Диаметр вала: квадратный 12×12 мм (доступны втулки 8×8 и 10×10 мм).",
            (
                "– Подберите модель по крутящему моменту (3–20 Нм) и площади заслонки "
                "(см. таблицу характеристик выбранного артикула)."
            ),
            "",
            "Инструменты:",
            ("– Ключи для фиксации адаптера, отвёртка для подключения проводов, мультиметр для проверки напряжения."),
            "",
            "2. Монтаж привода",
            "",
            "Крепление на вал:",
            ("– Закрепите привод на валу заслонки, соблюдая направление вращения (монтаж с противоположной стороны)."),
            "– Убедитесь в отсутствии перекоса: затяните крепёжные винты равномерно.",
            "",
            "Регулировка угла поворота:",
            "– Ограничьте угол поворота при необходимости (макс. 95°).",
            (
                "– Ручное управление: редуктор выводится из зацепления при помощи кнопки "
                "с самовозвратом, ручная блокировка."
            ),
            "",
            "3. Электрическое подключение",
            "",
            "Параметры питания:",
            "– Исполнения 24 В: AC/DC 24 В, 50/60 Гц (класс защиты III).",
            ("– Исполнения 230 В: AC 100…240 В, 50/60 Гц (класс защиты II — полная изоляция)."),
            "– Сечение провода: 0,5 мм².",
            "",
            "Схема подключения:",
            "– См. также чертёж «Схема подключения» в галерее и PDF инструкции.",
            "",
            "Двухпозиционное управление (открыто/закрыто):",
            ("– Подключите провода к клеммам питания: L и N для 230 В либо «+» и «−» для 24 В."),
            (
                "– Защитный проводник PE к приводу не подключается: исполнения 230 В — класс II "
                "(полная изоляция), отдельной клеммы заземления на корпусе нет."
            ),
            "",
            "Вспомогательные переключатели (-DS / -DST):",
            (
                "– Две группы (S1–S3 и S4–S6). Используйте контакты для индикации положения "
                "в системе управления зданием."
            ),
            "",
            "Термодатчик SAF72 (только -DST):",
            (
                "– TS1 размыкается при температуре окружающей среды выше 72 °C; "
                "TS2 — при температуре в канале выше 72 °C."
            ),
            "",
            "4. Управление и эксплуатация",
            "",
            "Режимы работы:",
            "– Двухпозиционный: сигнал включения/выключения для крайних положений клапана.",
            "",
            "Аварийный возврат пружиной:",
            (
                "– При отключении питания пружина возвращает клапан в исходное положение "
                "(время поворота двигателя и возврата пружины — см. характеристики артикула)."
            ),
            "",
            "5. Техника безопасности и обслуживание",
            "",
            "Защита:",
            "– Соблюдайте блок «ВНИМАНИЕ» в начале инструкции.",
            "– Не вскрывайте корпус — ремонт только у производителя.",
            "– Степень защиты корпуса: IP54.",
            "",
            "Эксплуатационные условия:",
            "– Температура окружающей среды: –20…+50 °C.",
            "– Температура хранения: –40…+70 °C.",
            "– Относительная влажность: 95 %, без конденсации.",
            "",
            "Обслуживание:",
            "– Регулярно проверяйте крепление на валу и чистоту контактов.",
            "",
            "Утилизация:",
            (
                "– Не утилизируйте привод как бытовые отходы; соблюдайте местные правила "
                "утилизации электрооборудования."
            ),
            "",
            "Рекомендации:",
            "– Для индикации положения используйте вспомогательные переключатели.",
            "– Для отключения по температуре выбирайте исполнение -DST (SAF72).",
            "– Класс защиты: III для 24 В, II для 230 В (без PE на приводе).",
        ],
    ),
)


def is_safu_sku(sku: SKU) -> bool:
    """True when the article is an SA…FU fire/smoke edition."""
    code = (sku.sku_code or "").strip()
    if _SAFU_CODE.match(code.replace(" ", "")):
        return True
    product = getattr(sku, "product", None)
    if product is not None and _SAFU_PRODUCT.search(product.slug or ""):
        return True
    return False


def parse_safu_torque_nm(sku_code: str) -> int | None:
    """Extract rated torque (Нм) from ``SA5FU24-DS`` → ``5``."""
    match = _SAFU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def instructions_for_safu_sku(sku_code: str) -> str | None:
    """Build install guide scoped to one SA..FU edition."""
    from catalog.etl.sku_instructions import format_damper_area, power_supply_bullets

    torque_nm = parse_safu_torque_nm(sku_code)
    if torque_nm is None:
        return None
    row = TORQUE_SPECS.get(torque_nm)
    if row is None:
        return None
    variant = parse_sku_variant(sku_code)
    thermal = sku_code_is_thermal(sku_code)
    series = f"SA{torque_nm}FU"
    lines: list[str] = [
        (f"Инструкция по установке и управлению приводом противопожарного клапана Hoocon {series}"),
        (f"Для корректной работы привода {series} соблюдайте рекомендации по монтажу, подключению и настройке."),
        "",
        *MANUAL_SAFETY_ATTENTION_LINES,
        "",
        "1. Подготовка к установке",
        "",
        "Проверка совместимости:",
        f"– Длина вала заслонки: {row['shaft-length']}.",
        "– Диаметр вала: квадратный 12×12 мм (доступны втулки 8×8 и 10×10 мм).",
        (f"– Крутящий момент: {row['moment']}; площадь заслонки {format_damper_area(row['damper-area'])}."),
        f"– Габаритные размеры: {row['dimensions']}.",
        "",
        "2. Монтаж привода",
        "",
        ("– Закрепите привод на валу заслонки, соблюдая направление вращения (монтаж с противоположной стороны)."),
        "– Убедитесь в отсутствии перекоса: затяните крепёжные винты равномерно.",
        "– Ограничьте угол поворота при необходимости (макс. 95°).",
        (
            "– Ручное управление: редуктор выводится из зацепления при помощи кнопки "
            "с самовозвратом, ручная блокировка."
        ),
        "",
        "3. Электрическое подключение",
        "",
        *power_supply_bullets(variant, class_ii_detail=True),
        "– Сечение провода: 0,5 мм².",
        "– Схемы подключения — в галерее («Схема подключения») и PDF инструкции.",
    ]
    if variant.voltage == "230":
        lines.append(
            "– Защитный проводник PE к приводу не подключается: класс II "
            "(полная изоляция), отдельной клеммы заземления на корпусе нет.",
        )
    lines.extend(
        [
            "",
            "4. Двухпозиционное управление",
            "",
            ("– Подключите провода к клеммам питания: L и N для 230 В либо «+» и «−» для 24 В."),
        ],
    )
    next_ch = 5
    if variant.aux_switch is True:
        lines.extend(
            [
                "",
                f"{next_ch}. Вспомогательные переключатели",
                "",
                ("– Две группы (S1–S3 и S4–S6). Используйте контакты для индикации положения в системе управления."),
            ],
        )
        next_ch += 1
    if thermal:
        lines.extend(
            [
                "",
                f"{next_ch}. Термодатчик SAF72",
                "",
                (
                    "– TS1 размыкается при температуре окружающей среды выше 72 °C; "
                    "TS2 — при температуре в канале выше 72 °C."
                ),
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


def safu_product_queryset() -> QuerySet[Product]:
    """Products that own at least one SA..FU SKU."""
    return Product.objects.filter(skus__sku_code__iregex=r"(?i)^sa\d+fu").distinct()


def _product_title(torque_nm: int) -> str:
    return f"SA{torque_nm}FU | Электропривод противопожарного клапана с пружинным возвратом, {torque_nm} Нм"


def _sku_description(variant: SkuVariant, torque_nm: int, spec: _TorqueSpec) -> str:
    lines = [
        (
            "Электропривод противопожарного / дымового клапана с пружинным возвратом. "
            f"Крутящий момент {spec['moment']}, площадь заслонки {spec['damper-area']}."
        ),
        ("Ручное управление: редуктор выводится из зацепления при помощи кнопки с самовозвратом, ручная блокировка."),
        "",
        "Управление: открыто/закрыто.",
        "Вспомогательные переключатели: 2 SPDT (исполнение S / -DS / -DST).",
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


def apply_safu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite all SA..FU products/SKUs from the fire/smoke datasheet canon.

    Args:
        dry_run: When True, count only (no writes).

    Returns:
        Counters: products, skus, attributes, dry_run.
    """
    products = list(safu_product_queryset().select_related("category"))
    skus_done = 0
    attrs = 0
    for product in products:
        skus = list(SKU.objects.filter(product=product, sku_code__iregex=r"(?i)^sa\d+fu"))
        torque_nm = None
        for sku in skus:
            torque_nm = parse_safu_torque_nm(sku.sku_code)
            if torque_nm is not None:
                break
        if torque_nm is None:
            continue
        spec = TORQUE_SPECS.get(torque_nm)
        if spec is None:
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

        category_slug = product.category.slug if product.category_id else ""
        for sku in skus:
            nm = parse_safu_torque_nm(sku.sku_code) or torque_nm
            row = TORQUE_SPECS.get(nm, spec)
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                sku.name = title[:300]
                sku.description = _sku_description(variant, nm, row)
                sku.specs_text = ""
                sku.save(update_fields=["name", "description", "specs_text"])
                _clear_sku_attributes(sku)

            for name, slug, unit, value, _group in SHARED_ATTRS:
                if not dry_run:
                    _set_attr(sku, name, slug, unit, value)
                attrs += 1

            torque_rows: tuple[AttrRow, ...] = (
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
                (
                    "Уровень шума",
                    "noise",
                    "дБ(A)",
                    row["noise"],
                    ATTR_GROUP_FUNCTIONAL,
                ),
                ("Масса", "weight", "кг", row["weight"], ATTR_GROUP_SIZE),
                (
                    "Габаритные размеры",
                    "dimensions",
                    "мм",
                    row["dimensions"],
                    ATTR_GROUP_SIZE,
                ),
                (
                    "Длина вала заслонки",
                    "shaft-length",
                    "мм",
                    row["shaft-length"],
                    ATTR_GROUP_SIZE,
                ),
                (
                    "Потребляемая мощность",
                    "power-consumption",
                    "",
                    row["power"],
                    ATTR_GROUP_ELECTRICAL,
                ),
            )
            for name, slug, unit, value, _group in torque_rows:
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

            if variant.control == "on_off":
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
                attrs += 1

            if variant.aux_switch is True:
                if not dry_run:
                    _set_attr(
                        sku,
                        "Вспомогательный переключатель",
                        "aux-switch",
                        "",
                        normalize_aux_switch_value("SPDT-2", sku_code=sku.sku_code),
                    )
                attrs += 1

            temp_value = TEMP_SENSOR_SAF72 if sku_code_is_thermal(sku.sku_code) else TEMP_SENSOR_NONE
            if not dry_run:
                _set_attr(sku, "Датчик температуры", "temp-sensor", "", temp_value)
            attrs += 1

            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "dry_run": dry_run,
    }
