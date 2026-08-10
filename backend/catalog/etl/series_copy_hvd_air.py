"""Canonical ТТХ for bare HVD air on/off (no spring, not Q/QX/F).

Source: existing HVD-5/10/20 catalog cards + 2022 AI album (HVD-40).
"""

from __future__ import annotations

import re
from typing import Any, Final

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.tech_copy import (
    CONTROL_ON_OFF,
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    normalize_tech_copy,
)
from catalog.facets.aux import aux_spdt_count_from_sku, normalize_aux_switch_value
from catalog.models import SKU, AttributeValue

_SKU_RE: Final[re.Pattern[str]] = re.compile(
    r"(?i)^hvd(?P<volt>24|230)(?P<aux>s)?-(?P<nm>\d+)$",
)

PRODUCT_NAME_TMPL = "HVD-{nm} | {nm} Нм Привод воздушный без возвратной пружины управление 2-/3-позиционное"

SERIES_DESCRIPTION = normalize_tech_copy(
    """
Электропривод HVD — устройство для управления воздушными заслонками
в системах вентиляции и кондиционирования без возвратной пружины.

Управление: открыто/закрыто, 2-/3-позиционное.
Исполнения с вспомогательными переключателями — суффикс S в коде.
""".strip(),
)

AttrRow = tuple[str, str, str, str]

_SHARED: Final[tuple[AttrRow, ...]] = (
    ("Ручное управление", "manual-override", "", MANUAL_OVERRIDE_BUTTON_SELF_RESET),
    ("Индикация положения", "position-indication", "", "механическая"),
    ("Угол поворота", "rotation-angle", "°", "0°…90°"),
    ("Уровень шума", "noise", "дБ(A)", "45 дБ"),
    ("Степень защиты", "ip-rating", "", "IP54"),
    ("Температура окружающей среды", "ambient-temp", "°C", "от -20 °С до +50 °С"),
    ("Температура хранения", "storage-temp", "°C", "от -30 °С до +80 °С"),
    ("Влажность", "humidity", "", "до 95% отн. влажности"),
    ("Сечение провода", "wire-cross-section", "мм²", "0,5 мм²"),
)

# Per-Nm from site HVD-5/20 cards + album HVD-40 (pp. 44–45).
TORQUE_SPECS: Final[dict[int, dict[str, str]]] = {
    5: {
        "moment": "5 Нм",
        "damper-area": "до 0,5 м²",
        "running-time": "≤ 60 с (90°)",
        "dimensions": "144,1 × 71,1 × 62,1 мм",
        "weight": "≤ 0,8 кг",
        "shaft-length": "≥ 50 мм",
        "transformer-va": "6,5 ВА",
        "power": "3,5 Вт (работа) / 0,5 Вт (удержание)",
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "running-time": "≤ 60 с (90°)",
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
        "shaft-length": "≥ 60 мм",
        "transformer-va": "8 ВА",
        "power": "4 Вт (работа) / 0,5 Вт (удержание)",
    },
    20: {
        "moment": "20 Нм",
        "damper-area": "до 2,0 м²",
        "running-time": "≤ 150 с (90°)",
        "dimensions": "191,8 × 103,4 × 68 мм",
        "weight": "≤ 1,4 кг",
        "shaft-length": "≥ 60 мм",
        "transformer-va": "10 ВА",
        "power": "4,5 Вт (работа) / 0,5 Вт (удержание)",
    },
    40: {
        "moment": "40 Нм",
        "damper-area": "до 4,0 м²",
        "running-time": "≤ 150 с (90°)",
        "dimensions": "198,6 × 110,2 × 68 мм",
        "weight": "≤ 1,5 кг",
        "shaft-length": "≥ 60 мм",
        "transformer-va": "12 ВА",
        "power": "5 Вт (работа) / 0,5 Вт (удержание)",
    },
}


def parse_hvd_air_bare(sku_code: str) -> tuple[int, str, bool] | None:
    """Return ``(nm, voltage, has_aux)`` for bare HVD (not Q/QX/F/QA)."""
    match = _SKU_RE.fullmatch((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    nm = int(match.group("nm"))
    if nm not in TORQUE_SPECS:
        return None
    return nm, match.group("volt"), bool(match.group("aux"))


def _set(sku: SKU, name: str, slug: str, unit: str, value: str) -> None:
    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)


def _enrich_sku(sku: SKU, *, nm: int, voltage: str, has_aux: bool, row: dict[str, str]) -> int:
    """Rewrite one bare HVD air SKU; return attribute write count."""
    title = PRODUCT_NAME_TMPL.format(nm=nm)
    variant = parse_sku_variant(sku.sku_code)
    sku.name = title[:300]
    sku.description = SERIES_DESCRIPTION
    sku.specs_text = ""
    sku.save(update_fields=["name", "description", "specs_text"])

    AttributeValue.objects.filter(sku=sku).delete()
    attrs = 0

    family: tuple[AttrRow, ...] = (
        ("Крутящий момент", "moment", "Нм", row["moment"]),
        ("Площадь заслонки", "damper-area", "м²", row["damper-area"]),
        ("Время поворота", "running-time", "с", row["running-time"]),
        ("Габаритные размеры", "dimensions", "мм", row["dimensions"]),
        ("Масса", "weight", "кг", row["weight"]),
        ("Длина вала заслонки", "shaft-length", "мм", row["shaft-length"]),
        ("Мощность трансформатора", "transformer-va", "В·А", row["transformer-va"]),
        ("Потребляемая мощность", "power-consumption", "Вт", row["power"]),
        ("Управление", "control", "", CONTROL_ON_OFF),
    )
    for name, slug, unit, value in (*family, *_SHARED):
        _set(sku, name, slug, unit, value)
        attrs += 1

    if voltage == "24":
        _set(sku, "Номинальное напряжение", "voltage", "В", "AC/DC 24 В, 50/60 Гц")
        _set(
            sku,
            "Класс защиты",
            "protection-class",
            "",
            "III (безопасное сверхнизкое напряжение)",
        )
    else:
        _set(sku, "Номинальное напряжение", "voltage", "В", "AC 100…240 В, 50/60 Гц")
        _set(sku, "Класс защиты", "protection-class", "", "II (полная изоляция)")
    attrs += 2

    if has_aux or variant.aux_switch is True:
        count = aux_spdt_count_from_sku(sku.sku_code) or 2
        _set(
            sku,
            "Вспомогательный переключатель",
            "aux-switch",
            "",
            normalize_aux_switch_value(f"SPDT-{count}", sku_code=sku.sku_code),
        )
        attrs += 1

    return attrs


def apply_hvd_air_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite bare HVD air Products/SKUs (5/10/20/40 Нм) with full ТТХ."""
    summary: dict[str, Any] = {
        "products": 0,
        "skus": 0,
        "attributes": 0,
        "dry_run": dry_run,
        "by_nm": {},
    }
    skus = list(
        SKU.objects.filter(sku_code__iregex=r"(?i)^hvd(?:24|230)s?-\d+$")
        .select_related("product", "product__category")
        .order_by("sku_code"),
    )
    touched_products: set[int] = set()
    for sku in skus:
        parsed = parse_hvd_air_bare(sku.sku_code or "")
        if parsed is None:
            continue
        nm, voltage, has_aux = parsed
        row = TORQUE_SPECS[nm]
        summary["skus"] += 1
        summary["by_nm"][nm] = summary["by_nm"].get(nm, 0) + 1
        if dry_run:
            continue

        product = sku.product
        if product is not None and product.pk not in touched_products:
            product.name = PRODUCT_NAME_TMPL.format(nm=nm)[:200]
            product.description = SERIES_DESCRIPTION
            product.specs_text = ""
            product.save(update_fields=["name", "description", "specs_text"])
            touched_products.add(product.pk)
            summary["products"] += 1

        summary["attributes"] += _enrich_sku(
            sku,
            nm=nm,
            voltage=voltage,
            has_aux=has_aux,
            row=row,
        )
    return summary
