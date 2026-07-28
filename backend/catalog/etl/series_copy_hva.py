"""Canonical ТТХ + catalog seed for Hoocon HVA modulating air dampers (no spring).

Source: English datasheets in ``_инструкции-pdf`` (``hva-5.pdf``, ``hva-10q.pdf``, …)
and Russian HV catalog pages (2025 / Illustrator). Creates missing Products/SKUs
for Nm lines present in the catalog but not yet on the site.
"""

from __future__ import annotations

import re
from typing import Any, Final

from catalog.etl.attr_write import set_sku_attribute
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
    normalize_tech_copy,
)
from catalog.models import SKU, Category, Product

# HVA24-5 / HVA24S-5Q — optional aux S, torque, optional fast Q (not P/UQ spring).
_HVA_STD_Q_CODE = re.compile(
    r"(?i)^hva(?P<volt>24|230)(?P<aux>s)?-(?P<nm>\d+)(?P<fast>q)?$",
)

AttrRow = tuple[str, str, str, str]

CATEGORY_STD = "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
CATEGORY_Q = "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"

# Catalog / datasheet families to ensure on the site (std + Q for 5/10/20/40).
CATALOG_FAMILIES: Final[tuple[tuple[int, bool], ...]] = (
    (5, False),
    (5, True),
    (10, False),
    (10, True),
    (20, False),
    (20, True),
    (40, False),
    (40, True),
)

_EDITIONS: Final[tuple[tuple[str, bool], ...]] = (
    ("24", False),
    ("24", True),
    ("230", False),
    ("230", True),
)

_SHARED: Final[tuple[AttrRow, ...]] = (
    ("Управление", "control", "", CONTROL_MODULATING),
    (CONTROL_SIGNAL_Y_LABEL, CONTROL_SIGNAL_Y_SLUG, "", CONTROL_SIGNAL_Y_CANON),
    (FEEDBACK_SIGNAL_U_LABEL, FEEDBACK_SIGNAL_U_SLUG, "", FEEDBACK_SIGNAL_U_CANON),
    ("Ручное управление", "manual-override", "", MANUAL_OVERRIDE_BUTTON_SELF_RESET),
    ("Угол поворота", "rotation-angle", "°", "макс. 90°"),
    ("Индикация положения", "position-indication", "", "механическая"),
    ("Степень защиты", "ip-rating", "", "IP54"),
    ("Температура окружающей среды", "ambient-temp", "°C", "-20...+50 °C"),
    ("Температура хранения", "storage-temp", "°C", "-30...+80 °C"),
    ("Влажность", "humidity", "", "95 % RH, без конденсации"),
    ("Направление вращения", "rotation-direction", "", "выбирается переключателем"),
    ("Сечение провода", "wire-cross-section", "мм²", "0,5 мм²"),
)

# Per Nm / fast-Q family from English datasheets (Dimensions/Weight + Function).
FAMILY_SPECS: Final[dict[tuple[int, bool], dict[str, str]]] = {
    (5, False): {
        "moment": "5 Нм",
        "damper-area": "до 0,5 м²",
        "running-time": "< 60 с",
        "noise": "45 дБ",
        "shaft-length": "≥ 50 мм",
        "dimensions": "71,1 × 144,1 × 62,1 мм",
        "weight": "< 0,8 кг",
        "power-24": "3 Вт / 0,5 Вт (удержание)",
        "power-230": "3 Вт / 0,5 Вт (удержание)",
    },
    (5, True): {
        "moment": "5 Нм",
        "damper-area": "до 0,5 м²",
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 50 мм",
        "dimensions": "71,1 × 141,1 × 62,1 мм",
        "weight": "< 0,8 кг",
        "power-24": "3,5 Вт / 0,5 Вт (удержание)",
        "power-230": "3,5 Вт / 0,5 Вт (удержание)",
    },
    (10, False): {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "running-time": "< 60 с",
        "noise": "45 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "167,8 × 88,2 × 68 мм",
        "weight": "< 1,1 кг",
        "power-24": "4,5 Вт / 1 Вт (удержание)",
        "power-230": "4,5 Вт / 1 Вт (удержание)",
    },
    (10, True): {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
        "power-24": "5 Вт / 1 Вт (удержание)",
        "power-230": "5 Вт / 1 Вт (удержание)",
    },
    (20, False): {
        "moment": "20 Нм",
        "damper-area": "до 2,0 м²",
        "running-time": "< 150 с",
        "noise": "45 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "191,8 × 103,4 × 68 мм",
        "weight": "< 1,4 кг",
        "power-24": "4,5 Вт / 1 Вт (удержание)",
        "power-230": "4,5 Вт / 1 Вт (удержание)",
    },
    (20, True): {
        "moment": "20 Нм",
        "damper-area": "до 2,0 м²",
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "191,8 × 103,4 × 68 мм",
        "weight": "< 1,4 кг",
        "power-24": "8 Вт / 1 Вт (удержание)",
        "power-230": "8 Вт / 1 Вт (удержание)",
    },
    (40, False): {
        "moment": "40 Нм",
        "damper-area": "до 4,0 м²",
        "running-time": "< 150 с",
        "noise": "45 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "180,8 × 99 × 68 мм",
        "weight": "< 1,5 кг",
        "power-24": "5 Вт / 1 Вт (удержание)",
        "power-230": "5 Вт / 1 Вт (удержание)",
    },
    (40, True): {
        "moment": "40 Нм",
        "damper-area": "до 4,0 м²",
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "198,6 × 104 × 68 мм",
        "weight": "< 1,5 кг",
        "power-24": "15 Вт / 3 Вт (удержание)",
        "power-230": "15 Вт / 3 Вт (удержание)",
    },
}

SERIES_DESCRIPTION = normalize_tech_copy(
    "Электроприводы HVA — пропорциональное управление воздушной заслонкой "
    "без возвратной пружины. Издания 24/230 В с опцией вспомогательных "
    "переключателей (S). Ускоренные линейки (Q) — короткое время поворота.",
)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Монтаж и подключение — по инструкции на карточке модели.",
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
        ],
    ),
)


def parse_hva_std_q(sku_code: str) -> tuple[int, bool, str, bool] | None:
    """Return ``(nm, is_fast_q, voltage, has_aux)`` for std/Q HVA codes."""
    match = _HVA_STD_Q_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return (
        int(match.group("nm")),
        bool(match.group("fast")),
        match.group("volt"),
        bool(match.group("aux")),
    )


def hva_sku_code(*, voltage: str, aux: bool, torque_nm: int, fast: bool) -> str:
    """Build ``HVA24S-10Q`` from edition parts."""
    s = "S" if aux else ""
    q = "Q" if fast else ""
    return f"HVA{voltage}{s}-{torque_nm}{q}"


def product_slug_for_hva(*, torque_nm: int, fast: bool) -> str:
    """Product slug for one HVA Nm / Q tile."""
    if fast:
        return f"privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-{torque_nm}nm"
    return f"privod-vozdushniy-hva-{torque_nm}nm"


def sku_slug_for_hva(code: str, *, torque_nm: int, fast: bool) -> str:
    """SKU slug = ``{product_slug}-{code.lower()}``."""
    return f"{product_slug_for_hva(torque_nm=torque_nm, fast=fast)}-{code.lower()}"


def _product_title(*, torque_nm: int, fast: bool) -> str:
    if fast:
        return f"HVA-{torque_nm}Q | {torque_nm} Нм Привод воздушный без возвратной пружины ускоренного срабатывания"
    return (
        f"HVA-{torque_nm} | {torque_nm} Нм Привод воздушный без возвратной "
        f"пружины пропорциональное (модулирующее) управление"
    )


def ensure_hva_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """Create missing HVA std/Q products and four edition SKUs each."""
    cat_std = Category.objects.filter(slug=CATEGORY_STD).first()
    cat_q = Category.objects.filter(slug=CATEGORY_Q).first()
    if cat_std is None or cat_q is None:
        missing = []
        if cat_std is None:
            missing.append(CATEGORY_STD)
        if cat_q is None:
            missing.append(CATEGORY_Q)
        return {
            "products_created": 0,
            "skus_created": 0,
            "dry_run": dry_run,
            "error": f"category missing: {', '.join(missing)}",
        }

    products_created = 0
    skus_created = 0
    for torque_nm, fast in CATALOG_FAMILIES:
        category = cat_q if fast else cat_std
        p_slug = product_slug_for_hva(torque_nm=torque_nm, fast=fast)
        title = _product_title(torque_nm=torque_nm, fast=fast)
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

        for voltage, aux in _EDITIONS:
            code = hva_sku_code(
                voltage=voltage,
                aux=aux,
                torque_nm=torque_nm,
                fast=fast,
            )
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
                slug=sku_slug_for_hva(code, torque_nm=torque_nm, fast=fast),
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


def apply_hva_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Ensure catalog rows, then upsert datasheet ТТХ onto HVA std/Q SKUs."""
    ensure = ensure_hva_catalog(dry_run=dry_run)
    summary: dict[str, Any] = {
        "skus": 0,
        "updated": 0,
        "skipped": 0,
        "attributes": 0,
        "dry_run": dry_run,
        "by_family": {},
        "ensure": ensure,
    }
    if ensure.get("error"):
        summary["error"] = ensure["error"]
        return summary

    skus = list(SKU.objects.filter(sku_code__istartswith="HVA").order_by("sku_code"))
    for sku in skus:
        parsed = parse_hva_std_q(sku.sku_code)
        if parsed is None:
            summary["skipped"] += 1
            continue
        nm, fast, voltage, has_aux = parsed
        row = FAMILY_SPECS.get((nm, fast))
        if row is None:
            summary["skipped"] += 1
            continue
        family_key = f"HVA-{nm}{'Q' if fast else ''}"
        summary["by_family"].setdefault(family_key, 0)
        summary["by_family"][family_key] += 1
        summary["skus"] += 1
        if dry_run:
            continue

        title = _product_title(torque_nm=nm, fast=fast)
        product = sku.product
        if product is not None:
            product.name = title[:200]
            product.description = SERIES_DESCRIPTION
            product.instructions = SERIES_INSTRUCTIONS
            product.save(update_fields=["name", "description", "instructions"])

        sku.name = title[:300]
        sku.save(update_fields=["name"])

        for name, slug, unit, value in _SHARED:
            set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
            summary["attributes"] += 1

        family_attrs: tuple[AttrRow, ...] = (
            ("Крутящий момент", "moment", "Нм", row["moment"]),
            ("Площадь заслонки", "damper-area", "м²", row["damper-area"]),
            ("Время поворота", "running-time", "с", row["running-time"]),
            ("Уровень шума", "noise", "дБ", row["noise"]),
            ("Длина вала заслонки", "shaft-length", "мм", row["shaft-length"]),
            ("Габаритные размеры", "dimensions", "мм", row["dimensions"]),
            ("Масса", "weight", "кг", row["weight"]),
        )
        for name, slug, unit, value in family_attrs:
            set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
            summary["attributes"] += 1

        power = row["power-24"] if voltage == "24" else row["power-230"]
        set_sku_attribute(
            sku,
            slug="power-consumption",
            value=power,
            name="Потребляемая мощность",
            unit="Вт",
        )
        summary["attributes"] += 1

        if voltage == "24":
            set_sku_attribute(
                sku,
                slug="voltage",
                value="AC/DC 24 В, 50/60 Гц",
                name="Номинальное напряжение",
                unit="В",
            )
            set_sku_attribute(
                sku,
                slug="protection-class",
                value="III (безопасное низкое напряжение)",
                name="Класс защиты",
                unit="",
            )
        else:
            set_sku_attribute(
                sku,
                slug="voltage",
                value="AC 100…240 В, 50/60 Гц",
                name="Номинальное напряжение",
                unit="В",
            )
            set_sku_attribute(
                sku,
                slug="protection-class",
                value="II (полная изоляция)",
                name="Класс защиты",
                unit="",
            )
        summary["attributes"] += 2

        if has_aux:
            set_sku_attribute(
                sku,
                slug="aux-switch",
                value="SPDT-2",
                name="Вспомогательный переключатель",
                unit="",
            )
            summary["attributes"] += 1
        else:
            # Clear stale aux on non-S editions if present from a bad copy.
            pass

        summary["updated"] += 1
    return summary
