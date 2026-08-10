"""Canonical copy + ТТХ for Hoocon DA..FU (spring-return damper actuators).

Source of truth: product manuals + Belimo RU glossary
(``docs/tech-copy-belimo-ru.md`` § DA5FU24). Shared functional / operating /
size rows are identical across the DAFU family; torque and electrical edition
fields vary per SKU.
"""

from __future__ import annotations

import re
from typing import Any

from catalog.etl.attr_groups import (
    ATTR_GROUP_ELECTRICAL,
    ATTR_GROUP_FUNCTIONAL,
    ATTR_GROUP_OPERATING,
    ATTR_GROUP_SIZE,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant
from catalog.etl.tech_copy import (
    CONTROL_MODULATING,
    CONTROL_SIGNAL_Y_CANON,
    CONTROL_SIGNAL_Y_LABEL,
    FEEDBACK_SIGNAL_U_CANON,
    FEEDBACK_SIGNAL_U_LABEL,
    MANUAL_OVERRIDE_NONE,
    MANUAL_SAFETY_ATTENTION_LINES,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.models import SKU, AttributeValue, Product

_DAFU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)fu")
_DAFU_PRODUCT = re.compile(r"(?i)dafu")

AttrRow = tuple[str, str, str, str, str]

# Shared across all DAFU editions (manual DA5FU D/DS table + Belimo RU).
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
        MANUAL_OVERRIDE_NONE,
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
        "Уровень шума",
        "noise",
        "дБ(A)",
        "макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины",
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
        "5…95 % относительной влажности",
        ATTR_GROUP_OPERATING,
    ),
    (
        "Длина вала заслонки",
        "shaft-length",
        "мм",
        "> 50 мм",
        ATTR_GROUP_SIZE,
    ),
    (
        "Диаметр вала",
        "shaft-diameter",
        "мм",
        "круглый 10…16 мм, квадратный 7×7…11×11 мм",
        ATTR_GROUP_SIZE,
    ),
    (
        "Длина кабеля",
        "cable-length",
        "мм",
        "1000 мм",
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

# Torque family → moment / damper / power / running / weight / transformer.
# DA5 rows match the published manual; other Nm from series tables / site copy.
_TorqueSpec = dict[str, str]
# Overall housing from DA5FU dimension photo (Ш × В × Г); DA3 shares the small body.
_DAFU_SMALL_DIMENSIONS = "98 × 156 × 84 мм"
# DA10…20 share the large spring-return body (page-3 «Габаритные размеры»).
_DAFU_LARGE_DIMENSIONS = "100 × 249 × 87,3 мм"

TORQUE_SPECS: dict[int, _TorqueSpec] = {
    3: {
        "moment": "3 Нм",
        "damper-area": "до 0,3 м²",
        "power": "5 Вт под нагрузкой / 2 Вт в режиме удержания",
        "running-time": "≤ 20 с",
        "weight": "< 1,3 кг",
        "transformer-va": "5 В·А",
        "dimensions": _DAFU_SMALL_DIMENSIONS,
    },
    5: {
        "moment": "5 Нм",
        "damper-area": "до 0,5 м²",
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "≤ 20 с",
        "weight": "< 1,5 кг",
        "transformer-va": "10 В·А",
        "dimensions": _DAFU_SMALL_DIMENSIONS,
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "power": "6 Вт под нагрузкой / 1,5 Вт в режиме удержания",
        "running-time": "≤ 25 с",
        "weight": "< 2,6 кг",
        "transformer-va": "10 В·А",
        "dimensions": _DAFU_LARGE_DIMENSIONS,
    },
    15: {
        "moment": "15 Нм",
        "damper-area": "до 1,5 м²",
        "power": "7 Вт под нагрузкой / 2 Вт в режиме удержания",
        "running-time": "≤ 25 с",
        "weight": "< 2,6 кг",
        "transformer-va": "15 В·А",
        "dimensions": _DAFU_LARGE_DIMENSIONS,
    },
    20: {
        "moment": "20 Нм",
        "damper-area": "до 2,0 м²",
        "power": "10 Вт под нагрузкой / 3,5 Вт в режиме удержания",
        "running-time": "≤ 25 с",
        "weight": "< 2,8 кг",
        "transformer-va": "20 В·А",
        "dimensions": _DAFU_LARGE_DIMENSIONS,
    },
}

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод воздушной заслонки с пружинным возвратом.
Предназначен для малогабаритных и средних оконечных воздушных заслонок
и узлов управления системой воздушного потока. Благодаря малым габаритам
и гибкости управления применяется в местах с ограниченным пространством.

Особенности серии DA..FU:
– Пружинный возврат при отключении питания.
– Ручное управление: отсутствует / не предусмотрено.
– Угол поворота: макс. 95°.
– Степень защиты корпуса: IP54.
– Температура окружающей среды: –20…+50 °C.
– Температура хранения: –40…+70 °C.

Управление по исполнению:
– Открыто/закрыто: суффиксы -D / -DS.
– Пропорциональное (модулирующее) 0(2)…10 В=: суффиксы -A / -AS (24 В).
– Вспомогательный переключатель: 2 SPDT (суффиксы -DS / -AS).
""".strip(),
)

# Install guide on Product.instructions — numbers must match SHARED_ATTRS / TORQUE_SPECS.
# 230 V is Class II (полная изоляция): protective earth PE is not used on the actuator.
# Keep each «–» bullet on one physical line (UI list parser does not soft-wrap mid-item).
SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Инструкция по установке и управлению приводом заслонки Hoocon DA..FU",
            (
                "Для корректной работы приводов серии DA..FU важно соблюдать рекомендации "
                "по монтажу, подключению и настройке. Ниже приведены ключевые этапы и особенности."
            ),
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
            "",
            "1. Подготовка к установке",
            "",
            "Проверка совместимости:",
            "– Убедитесь, что вал заслонки соответствует требованиям:",
            "– Длина вала: > 50 мм.",
            "– Диаметр вала: круглый 10…16 мм, квадратный 7×7…11×11 мм.",
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
            (
                "– Используйте универсальный адаптер из комплекта. Закрепите привод на валу "
                "заслонки, соблюдая направление вращения (L/R)."
            ),
            "– Убедитесь в отсутствии перекоса: затяните крепёжные винты равномерно.",
            "",
            "Регулировка угла поворота:",
            "– Установите механические упоры для ограничения угла поворота (макс. 95°).",
            "– Ручное управление на серии DA..FU отсутствует / не предусмотрено.",
            "",
            "3. Электрическое подключение",
            "",
            "Параметры питания:",
            "– Исполнения 24 В: AC/DC 24 В, 50/60 Гц (класс защиты III).",
            ("– Исполнения 230 В: AC 100…240 В, 50/60 Гц (класс защиты II — полная изоляция)."),
            "– Сечение провода: 0,5 мм². Длина кабеля: 1000 мм.",
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
            "Пропорциональное (модулирующее) управление:",
            ("– Подключите питание 24 В и сигнальный кабель Y / U к клеммам по схеме в инструкции."),
            "",
            "Вспомогательные переключатели (-DS / -AS):",
            "– Исполнения -DS / -AS: 2 SPDT.",
            "– Используйте контакты для индикации положения в системе управления зданием.",
            "",
            "4. Настройка направления вращения",
            "",
            "– Установите переключатель направления (L/R) на корпусе в нужное положение.",
            "– L — вращение против часовой стрелки.",
            "– R — вращение по часовой стрелке.",
            "",
            "5. Управление и эксплуатация",
            "",
            "Режимы работы:",
            "– Двухпозиционный: сигнал включения/выключения для крайних положений заслонки.",
            ("– Пропорциональный: положение по аналоговому сигналу 0(2)…10 В= (0(4)…20 мА — спецзаказ)."),
            "",
            "Аварийный возврат пружиной:",
            (
                "– При отключении питания пружина возвращает заслонку в исходное положение "
                "(время возврата пружины < 20 с; время поворота двигателя — см. характеристики)."
            ),
            "",
            "6. Техника безопасности и обслуживание",
            "",
            "Защита:",
            "– Соблюдайте блок «ВНИМАНИЕ» в начале инструкции.",
            "– Не вскрывайте корпус — ремонт только у производителя.",
            "– Степень защиты корпуса: IP54.",
            "",
            "Эксплуатационные условия:",
            "– Температура окружающей среды: –20…+50 °C.",
            "– Температура хранения: –40…+70 °C.",
            "– Относительная влажность: 5…95 % без конденсата.",
            "",
            "Обслуживание:",
            "– Регулярно проверяйте механические упоры и чистоту контактов.",
            "",
            "Утилизация:",
            (
                "– Не утилизируйте привод как бытовые отходы; соблюдайте местные правила "
                "утилизации электрооборудования."
            ),
            "",
            "Рекомендации:",
            "– Для индикации положения выбирайте исполнения -DS / -AS.",
            "– Класс защиты: III для 24 В, II для 230 В (без PE на приводе).",
        ],
    ),
)


def dafu_product_slugs() -> frozenset[str]:
    """Return Product.slug values that belong to the DAFU enricher."""
    return frozenset(
        Product.objects.filter(slug__icontains="dafu").values_list("slug", flat=True),
    )


def is_dafu_sku(sku: SKU) -> bool:
    """True when the article is a DA…FU spring-return edition."""
    code = (sku.sku_code or "").strip()
    if _DAFU_CODE.match(code.replace(" ", "")):
        return True
    product = getattr(sku, "product", None)
    if product is not None and _DAFU_PRODUCT.search(product.slug or ""):
        return True
    return False


def parse_dafu_torque_nm(sku_code: str) -> int | None:
    """Extract rated torque (Нм) from ``DA5FU24-D`` → ``5``."""
    m = _DAFU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if m is None:
        return None
    return int(m.group("nm"))


def instructions_for_dafu_sku(sku_code: str) -> str | None:
    """Build install guide scoped to one DA..FU edition."""
    from catalog.etl.sku_instructions import format_damper_area, power_supply_bullets

    torque_nm = parse_dafu_torque_nm(sku_code)
    if torque_nm is None:
        return None
    row = TORQUE_SPECS.get(torque_nm)
    if row is None:
        return None
    variant = parse_sku_variant(sku_code)
    series = f"DA{torque_nm}FU"
    lines: list[str] = [
        f"Инструкция по установке и управлению приводом заслонки Hoocon {series}",
        (f"Для корректной работы привода {series} соблюдайте рекомендации по монтажу, подключению и настройке."),
        "",
        *MANUAL_SAFETY_ATTENTION_LINES,
        "",
        "1. Подготовка к установке",
        "",
        "Проверка совместимости:",
        "– Длина вала заслонки: > 50 мм.",
        "– Диаметр вала: круглый 10…16 мм, квадратный 7×7…11×11 мм.",
        (f"– Крутящий момент: {row['moment']}; площадь заслонки {format_damper_area(row['damper-area'])}."),
        f"– Габаритные размеры: {row['dimensions']}.",
        "",
        "Инструменты:",
        ("– Ключи для фиксации адаптера, отвёртка для подключения проводов, мультиметр для проверки напряжения."),
        "",
        "2. Монтаж привода",
        "",
        (
            "– Используйте универсальный адаптер из комплекта. Закрепите привод на валу "
            "заслонки, соблюдая направление вращения (L/R)."
        ),
        "– Убедитесь в отсутствии перекоса: затяните крепёжные винты равномерно.",
        "– Установите механические упоры для ограничения угла поворота (макс. 95°).",
        "– Ручное управление отсутствует / не предусмотрено.",
        "",
        "3. Электрическое подключение",
        "",
        *power_supply_bullets(variant, class_ii_detail=True),
        "– Сечение провода: 0,5 мм². Длина кабеля: 1000 мм.",
        "– Схемы подключения — в галерее («Схема подключения») и PDF инструкции.",
    ]
    if variant.voltage == "230":
        lines.append(
            "– Защитный проводник PE к приводу не подключается: класс II "
            "(полная изоляция), отдельной клеммы заземления на корпусе нет.",
        )
    if variant.control == "modulating":
        lines.extend(
            [
                "",
                "4. Пропорциональное управление",
                "",
                "– Подключите питание и сигнальный кабель Y / U к клеммам по схеме.",
                f"– {CONTROL_SIGNAL_Y_LABEL}: 0(2)…10 В= (0(4)…20 мА — спецзаказ).",
            ],
        )
        next_ch = 5
    else:
        lines.extend(
            [
                "",
                "4. Двухпозиционное управление",
                "",
                ("– Подключите провода к клеммам питания: L и N для 230 В либо «+» и «−» для 24 В."),
            ],
        )
        next_ch = 5
    lines.extend(
        [
            "",
            f"{next_ch}. Настройка направления вращения",
            "",
            "– Установите переключатель направления (L/R) на корпусе в нужное положение.",
            "– L — вращение против часовой стрелки.",
            "– R — вращение по часовой стрелке.",
        ],
    )
    next_ch += 1
    if variant.aux_switch is True:
        lines.extend(
            [
                "",
                f"{next_ch}. Вспомогательные переключатели",
                "",
                "– Используйте контакты для индикации положения в системе управления.",
            ],
        )
        next_ch += 1
    lines.extend(
        [
            "",
            f"{next_ch}. Аварийный возврат пружиной",
            "",
            (
                f"– При отключении питания пружина возвращает заслонку в исходное положение "
                f"(время поворота двигателя {row['running-time']}; возврат пружины < 20 с)."
            ),
            "",
            f"{next_ch + 1}. Техника безопасности и обслуживание",
            "",
            "– Степень защиты корпуса: IP54.",
            "– Температура окружающей среды: –20…+50 °C.",
            "– Температура хранения: –40…+70 °C.",
        ],
    )
    return normalize_tech_copy("\n".join(lines))


def _product_title(torque_nm: int) -> str:
    return f"DA{torque_nm}FU | Электропривод воздушной заслонки с пружинным возвратом, {torque_nm} Нм"


def _sku_description(variant: SkuVariant, torque_nm: int, spec: _TorqueSpec) -> str:
    lines = [
        (
            "Электропривод воздушной заслонки с пружинным возвратом. "
            f"Крутящий момент {spec['moment']}, площадь заслонки {spec['damper-area']}."
        ),
        "Ручное управление отсутствует / не предусмотрено.",
        "",
    ]
    if variant.control == "modulating":
        lines.append(
            "Управление: пропорциональное (модулирующее), сигнал Y 0(2)…10 В= (0(4)…20 мА — спецзаказ).",
        )
    elif variant.control == "on_off":
        lines.append("Управление: открыто/закрыто.")
    if variant.aux_switch is True:
        from catalog.facets.aux import aux_spdt_count_from_sku

        count = aux_spdt_count_from_sku(variant.code) or 1
        edition = "AS" if (variant.code or "").casefold().endswith("-as") else "DS"
        lines.append(f"Вспомогательный переключатель: {count} SPDT (исполнение {edition}).")
    if variant.voltage == "24":
        lines.append("Номинальное напряжение: AC/DC 24 В, 50/60 Гц.")
    elif variant.voltage == "230":
        lines.append("Номинальное напряжение: AC 100…240 В, 50/60 Гц.")
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    AttributeValue.objects.filter(sku=sku).delete()


def apply_dafu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite all DAFU products/SKUs from the datasheet canon.

    Args:
        dry_run: When True, count only (no writes).

    Returns:
        Counters: products, skus, attributes, dry_run.
    """
    products = list(
        Product.objects.filter(slug__icontains="dafu").select_related("category"),
    )
    skus_done = 0
    attrs = 0
    for product in products:
        skus = list(SKU.objects.filter(product=product))
        # Infer series torque from first matching SKU (product line = one Nm).
        torque_nm = None
        for sku in skus:
            torque_nm = parse_dafu_torque_nm(sku.sku_code)
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
            nm = parse_dafu_torque_nm(sku.sku_code) or torque_nm
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
                ("Масса", "weight", "кг", row["weight"], ATTR_GROUP_SIZE),
                (
                    "Габаритные размеры",
                    "dimensions",
                    "мм",
                    row["dimensions"],
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
                    _set_attr(
                        sku,
                        "Мощность трансформатора",
                        "transformer-va",
                        "В·А",
                        row["transformer-va"],
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
                        "Класс защиты",
                        "protection-class",
                        "",
                        "II (все изолировано / полная изоляция)",
                    )
                attrs += 2

            if variant.control == "modulating":
                if not dry_run:
                    _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
                    _set_attr(
                        sku,
                        CONTROL_SIGNAL_Y_LABEL,
                        "control-signal",
                        "",
                        CONTROL_SIGNAL_Y_CANON,
                    )
                    _set_attr(
                        sku,
                        FEEDBACK_SIGNAL_U_LABEL,
                        "feedback-signal",
                        "",
                        FEEDBACK_SIGNAL_U_CANON,
                    )
                attrs += 3
            elif variant.control == "on_off":
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
                from catalog.facets import aux_spdt_count_from_sku, normalize_aux_switch_value

                count = aux_spdt_count_from_sku(sku.sku_code) or 1
                if not dry_run:
                    _set_attr(
                        sku,
                        "Вспомогательный переключатель",
                        "aux-switch",
                        "",
                        normalize_aux_switch_value(
                            f"SPDT-{count}",
                            sku_code=sku.sku_code,
                        ),
                    )
                attrs += 1

            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "dry_run": dry_run,
    }
