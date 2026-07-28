"""Canonical copy + ТТХ for Hoocon DA..MU (damper actuators, no spring return).

Source: English manuals in ``_инструкции-pdf`` (``da2mu-*.pdf``,
``da4_6mu-*.pdf``, ``da8_16_24_32mu*.pdf``) + Belimo RU glossary.
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
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant
from catalog.etl.tech_copy import (
    CONTROL_MODULATING,
    CONTROL_SIGNAL_Y_CANON,
    CONTROL_SIGNAL_Y_LABEL,
    CONTROL_SIGNAL_Y_SLUG,
    FEEDBACK_SIGNAL_U_CANON,
    FEEDBACK_SIGNAL_U_LABEL,
    FEEDBACK_SIGNAL_U_SLUG,
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    MANUAL_SAFETY_ATTENTION_LINES,
    normalize_control_attribute_value,
    normalize_tech_copy,
)
from catalog.facets import normalize_aux_switch_value
from catalog.models import SKU, AttributeValue, Product

_DAMU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)mu(?!q)")
_DAMU_PRODUCT = re.compile(r"(?i)damu|bez-pruzhin")

AttrRow = tuple[str, str, str, str, str]

SHARED_ATTRS: tuple[AttrRow, ...] = (
    (
        "Направление вращения",
        "rotation-direction",
        "",
        "выбирается переключателем",
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
        "Уровень шума",
        "noise",
        "дБ(A)",
        "макс. 45 дБ(А)",
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
        "Длина вала заслонки",
        "shaft-length",
        "мм",
        "≥ 50",
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

# Per-torque rows from English manuals (page 2 ТТХ + dimension crops).
# Envelope W × H × D from «Actuator Dimensions» drawings (same body for 4/6 and 8…32).
_DAMU_DIMS_2: Final[str] = "66 × 116 × 59 мм"
_DAMU_DIMS_4_6: Final[str] = "84,8 × 145,6 × 65 мм"
_DAMU_DIMS_8_32: Final[str] = "100 × 180 × 68 мм"

TORQUE_SPECS: dict[int, dict[str, str]] = {
    2: {
        "moment": "2 Нм",
        "damper-area": "до 0,2 м²",
        "running-time": "< 30 с (95°)",
        "ip-rating": "IP54",
        "shaft-diameter": "круглый 8…16 мм или квадратный 8×8 — 12×12 мм",
        "dimensions": _DAMU_DIMS_2,
        "weight": "< 0,5 кг",
        "aux_groups": "1",
        "power_24": "3 Вт (работа) / 0,5 Вт (удержание)",
        "power_230": "3 Вт (работа) / 0,7 Вт (удержание)",
    },
    4: {
        "moment": "4 Нм",
        "damper-area": "до 0,4 м²",
        "running-time": "< 50 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 8…16 мм / квадратный 8×8…12×12 мм",
        "dimensions": _DAMU_DIMS_4_6,
        "weight": "< 0,7 кг",
        "aux_groups": "2",
        "power_24": "3 Вт (работа) / 0,5 Вт (удержание)",
        "power_230": "3 Вт (работа) / 0,8 Вт (удержание)",
    },
    6: {
        "moment": "6 Нм",
        "damper-area": "до 0,6 м²",
        "running-time": "< 70 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 8…16 мм / квадратный 8×8…12×12 мм",
        "dimensions": _DAMU_DIMS_4_6,
        "weight": "< 0,7 кг",
        "aux_groups": "2",
        "power_24": "3 Вт (работа) / 0,5 Вт (удержание)",
        "power_230": "3 Вт (работа) / 0,8 Вт (удержание)",
    },
    8: {
        "moment": "8 Нм",
        "damper-area": "до 0,8 м²",
        "running-time": "< 55 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 10…20 мм / квадратный 10×10…16×16 мм",
        "dimensions": _DAMU_DIMS_8_32,
        "weight": "≈ 1,3 кг",
        "aux_groups": "2",
        "power_24": "4,5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "4,5 Вт (работа) / 1 Вт (удержание)",
    },
    16: {
        "moment": "16 Нм",
        "damper-area": "до 1,6 м²",
        "running-time": "< 100 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 10…20 мм / квадратный 10×10…16×16 мм",
        "dimensions": _DAMU_DIMS_8_32,
        "weight": "≈ 1,3 кг",
        "aux_groups": "2",
        "power_24": "4,5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "4,5 Вт (работа) / 1 Вт (удержание)",
    },
    24: {
        "moment": "24 Нм",
        "damper-area": "до 2,4 м²",
        "running-time": "< 160 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 10…20 мм / квадратный 10×10…16×16 мм",
        "dimensions": _DAMU_DIMS_8_32,
        "weight": "≈ 1,3 кг",
        "aux_groups": "2",
        "power_24": "4,5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "4,5 Вт (работа) / 1 Вт (удержание)",
    },
    32: {
        "moment": "32 Нм",
        "damper-area": "до 3,2 м²",
        "running-time": "< 180 с (95°)",
        "ip-rating": "IP44",
        "shaft-diameter": "круглый 10…20 мм / квадратный 10×10…16×16 мм",
        "dimensions": _DAMU_DIMS_8_32,
        "weight": "≈ 1,3 кг",
        "aux_groups": "2",
        "power_24": "4,5 Вт (работа) / 1 Вт (удержание)",
        "power_230": "4,5 Вт (работа) / 1 Вт (удержание)",
    },
}

# Shared PDP sections (product + SKU descriptions).
_APPLICATION_SECTION: Final[str] = "\n".join(
    [
        "Сфера применения:",
        "– Системы общеобменной вентиляции",
        "– Кондиционирование воздуха",
        "– Приточно-вытяжные установки",
        "– Климатическое оборудование",
        "– Промышленные вентиляционные системы",
    ],
)

_COMPETITIVE_SECTION: Final[str] = "\n".join(
    [
        "Конкурентные преимущества перед аналогами:",
        "– Более высокая точность позиционирования заслонки",
        "– Улучшенная защита от пыли и влаги",
        "– Расширенный диапазон рабочих температур",
        "– Повышенная надёжность механических компонентов",
        "– Более длительный срок службы",
        "– Лучшая совместимость с различными типами клапанов",
        "– Оптимизированное энергопотребление",
        "– Простота интеграции в системы автоматизации",
    ],
)

SERIES_DESCRIPTION = normalize_tech_copy(
    "\n".join(
        [
            "Электропривод воздушной заслонки без возвратной пружины.",
            "Используется для управления воздушными регулирующими заслонками",
            "в системах ОВК (отопления, вентиляции и кондиционирования).",
            "",
            "Назначение и особенности серии DA..MU:",
            ("– Без возвратной пружины: положение заслонки сохраняется при отключении питания."),
            "– Крутящий момент: 2…32 Нм (по модели).",
            ("– Управление: 2-/3-позиционное (-D/-DS) или пропорциональное 0(2)…10 В= (-A/-AS)."),
            "– Вспомогательные переключатели: исполнения -AS / -DS.",
            "– Степень защиты: IP54 (DA2MU) или IP44 (DA4…DA32MU).",
            "– Температура окружающей среды: –20…+50 °C.",
            "",
            _APPLICATION_SECTION,
            "",
            _COMPETITIVE_SECTION,
        ],
    ),
)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Инструкция по установке и управлению приводом заслонки Hoocon DA..MU",
            (
                "Для корректной работы приводов серии DA..MU соблюдайте рекомендации "
                "по монтажу, подключению и настройке."
            ),
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
            "",
            "1. Подготовка к установке",
            "",
            "Проверка совместимости:",
            "– Длина вала заслонки: ≥ 50 мм.",
            "– Диаметр вала — см. таблицу характеристик выбранного артикула.",
            "– Подберите модель по крутящему моменту и площади заслонки.",
            "",
            "2. Монтаж привода",
            "",
            "– Закрепите привод на валу заслонки штатным зажимом.",
            "– Убедитесь в отсутствии перекоса; затяните крепёж равномерно.",
            "– Ручное управление: кнопка с самовозвратом редуктора.",
            "",
            "3. Электрическое подключение",
            "",
            "– Исполнения 24 В: AC/DC 24 В, 50/60 Гц (класс защиты III).",
            "– Исполнения 230 В: AC 100…240 В, 50/60 Гц (класс защиты II).",
            "– Сечение провода: 0,5 мм².",
            "– Схемы подключения — в галерее («Схема подключения») и PDF инструкции.",
            "",
            "4. Настройка направления вращения",
            "",
            "– Установите переключатель направления на корпусе в нужное положение.",
            "",
            "5. Вспомогательные переключатели (-AS / -DS)",
            "",
            "– Настройте угол срабатывания по заводской таблице в инструкции.",
            "– Используйте контакты для индикации положения в системе управления.",
        ],
    ),
)


def instructions_for_damu_sku(sku_code: str) -> str | None:
    """Build install guide scoped to one DA..MU edition (voltage / aux / torque).

    Args:
        sku_code: Catalog SKU code, e.g. ``DA4MU230-AS``.

    Returns:
        Normalized instruction text, or ``None`` when the code is not DA..MU.
    """
    from catalog.etl.sku_instructions import format_damper_area, power_supply_bullets

    torque_nm = parse_damu_torque_nm(sku_code)
    if torque_nm is None:
        return None
    row = TORQUE_SPECS.get(torque_nm)
    if row is None:
        return None
    variant = parse_sku_variant(sku_code)
    series = f"DA{torque_nm}MU"
    lines: list[str] = [
        f"Инструкция по установке и управлению приводом заслонки Hoocon {series}",
        (f"Для корректной работы привода {series} соблюдайте рекомендации по монтажу, подключению и настройке."),
        "",
        *MANUAL_SAFETY_ATTENTION_LINES,
        "",
        "1. Подготовка к установке",
        "",
        "Проверка совместимости:",
        "– Длина вала заслонки: ≥ 50 мм.",
        f"– Диаметр вала: {row['shaft-diameter']}.",
        (f"– Крутящий момент: {row['moment']}; площадь заслонки {format_damper_area(row['damper-area'])}."),
        f"– Габаритные размеры: {row['dimensions']}.",
        "",
        "2. Монтаж привода",
        "",
        "– Закрепите привод на валу заслонки штатным зажимом.",
        "– Убедитесь в отсутствии перекоса; затяните крепёж равномерно.",
        "– Ручное управление: кнопка с самовозвратом редуктора.",
        "",
        "3. Электрическое подключение",
        "",
        *power_supply_bullets(variant),
        "– Сечение провода: 0,5 мм².",
        "– Схемы подключения — в галерее («Схема подключения») и PDF инструкции.",
        "",
        "4. Настройка направления вращения",
        "",
        "– Установите переключатель направления на корпусе в нужное положение.",
    ]
    if variant.control == "modulating":
        lines.extend(
            [
                "",
                "5. Пропорциональное управление",
                "",
                f"– {CONTROL_SIGNAL_Y_LABEL}: 0(2)…10 В= / 0(4)…20 мА.",
                "– Обратная связь U: 0(2)…10 В= / 0(4)…20 мА (по схеме в инструкции).",
            ],
        )
        next_ch = 6
    elif variant.control == "on_off":
        lines.extend(
            [
                "",
                "5. Двухпозиционное управление",
                "",
                "– Управление: 2-/3-позиционное (открыто/закрыто) по схеме в инструкции.",
            ],
        )
        next_ch = 6
    else:
        next_ch = 5
    if variant.aux_switch is True:
        aux_n = row["aux_groups"]
        aux_word = "группу" if aux_n == "1" else "группы"
        lines.extend(
            [
                "",
                f"{next_ch}. Вспомогательные переключатели",
                "",
                (f"– Исполнение включает {aux_n} {aux_word} вспомогательных переключателей SPDT."),
                "– Настройте угол срабатывания по заводской таблице в инструкции.",
                "– Используйте контакты для индикации положения в системе управления.",
            ],
        )
    return normalize_tech_copy("\n".join(lines))


def parse_damu_torque_nm(sku_code: str) -> int | None:
    """Return torque family from ``DA8MU24-D`` → ``8``."""
    match = _DAMU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def is_damu_sku(sku_code: str) -> bool:
    """True for DA..MU (not MQU) SKU codes."""
    return parse_damu_torque_nm(sku_code) is not None


def damu_product_queryset() -> QuerySet[Product]:
    """Products that host DA..MU SKUs."""
    return (
        Product.objects.filter(skus__sku_code__iregex=r"(?i)^da[0-9]+mu")
        .exclude(
            skus__sku_code__iregex=r"(?i)^da[0-9]+mqu",
        )
        .distinct()
    )


def _product_title(torque_nm: int) -> str:
    return f"DA{torque_nm}MU | Электропривод воздушный без возвратной пружины, {torque_nm} Нм"


def _sku_description(variant: SkuVariant, torque_nm: int, row: dict[str, str]) -> str:
    from catalog.etl.sku_instructions import format_damper_area

    lines = [
        (
            "Электропривод воздушной заслонки без возвратной пружины "
            f"({row['moment']}, площадь заслонки {format_damper_area(row['damper-area'])}). "
            "Используется для управления воздушными регулирующими заслонками "
            "в системах ОВК (отопления, вентиляции и кондиционирования)."
        ),
        "",
        "Особенности исполнения:",
        ("– Без возвратной пружины: положение заслонки сохраняется при отключении питания."),
    ]
    if variant.control == "modulating":
        lines.append("– Управление: пропорциональное (модулирующее) 0(2)…10 В=.")
    elif variant.control == "on_off":
        lines.append("– Управление: 2-/3-позиционное (открыто/закрыто).")
    if variant.aux_switch is True:
        lines.append(
            f"– Вспомогательные переключатели: {row['aux_groups']} группа(ы) SPDT.",
        )
    else:
        lines.append("– Вспомогательные переключатели: без доп. группы SPDT.")
    if variant.voltage == "24":
        lines.append("– Номинальное напряжение: AC/DC 24 В.")
    elif variant.voltage == "230":
        lines.append("– Номинальное напряжение: AC 100…240 В.")
    lines.extend(
        [
            "",
            _APPLICATION_SECTION,
            "",
            _COMPETITIVE_SECTION,
        ],
    )
    return normalize_tech_copy("\n".join(lines))


def _set_attr(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _clear_sku_attributes(sku: SKU) -> None:
    AttributeValue.objects.filter(sku=sku).delete()


def apply_damu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite all DA..MU products/SKUs from English-manual ТТХ.

    Args:
        dry_run: When True, count only (no writes).

    Returns:
        Counters: products, skus, attributes, dry_run.
    """
    products = list(damu_product_queryset().select_related("category"))
    skus_done = 0
    attrs = 0
    for product in products:
        skus = [s for s in SKU.objects.filter(product=product) if is_damu_sku(s.sku_code)]
        torque_nm = None
        for sku in skus:
            torque_nm = parse_damu_torque_nm(sku.sku_code)
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
            nm = parse_damu_torque_nm(sku.sku_code) or torque_nm
            row = TORQUE_SPECS.get(nm)
            if row is None:
                continue
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                sku.name = _product_title(nm)[:300]
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
                    "Степень защиты корпуса",
                    "ip-rating",
                    "",
                    row["ip-rating"],
                    ATTR_GROUP_OPERATING,
                ),
                (
                    "Диаметр вала",
                    "shaft-diameter",
                    "мм",
                    row["shaft-diameter"],
                    ATTR_GROUP_SIZE,
                ),
                (
                    "Габаритные размеры",
                    "dimensions",
                    "мм",
                    row["dimensions"],
                    ATTR_GROUP_SIZE,
                ),
                ("Масса", "weight", "кг", row["weight"], ATTR_GROUP_SIZE),
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

            if variant.control == "modulating":
                if not dry_run:
                    _set_attr(sku, "Управление", "control", "", CONTROL_MODULATING)
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
                attrs += 3
            elif variant.control == "on_off":
                if not dry_run:
                    _set_attr(
                        sku,
                        "Управление",
                        "control",
                        "",
                        normalize_control_attribute_value("2-/3-позиционное"),
                    )
                attrs += 1

            if variant.aux_switch is True:
                aux_val = normalize_aux_switch_value(
                    f"SPDT-{row['aux_groups']}",
                    sku_code=sku.sku_code,
                )
                if not dry_run:
                    _set_attr(
                        sku,
                        "Вспомогательный переключатель",
                        "aux-switch",
                        "",
                        aux_val,
                    )
                attrs += 1

            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "dry_run": dry_run,
    }
