"""Canonical copy + ТТХ for Hoocon SA..FQU (fast spring-return fire/smoke actuators).

Source: English manuals ``sa{n}fqu-ds_dst.pdf`` (factory EN drop 2026).
FQU shares the SAFU body family but shorter stroke (~35 s) and higher holding
power on small Nm vs classic FU tables.
"""

from __future__ import annotations

import re
from typing import Any

from django.db import transaction

from catalog.etl.attr_write import cached_attributes, clear_etl_attributes, set_sku_attribute, write_copy
from catalog.etl.series_copy_safu import SERIES_DESCRIPTION, SHARED_ATTRS
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant, sku_code_is_thermal
from catalog.etl.tech_copy import PROTECTION_CLASS_II, PROTECTION_CLASS_III, normalize_tech_copy
from catalog.models import SKU, Category, Product

_SAFQU_CODE = re.compile(r"(?i)^sa(?P<nm>\d+)fqu")

CATEGORY_SLUG = "elektroprivody-protivopozharnye-i-dymovye"

_TorqueSpec = dict[str, str]
_SAFU_SMALL_DIMENSIONS = "132 × 87 × 59 мм"
_SAFU_LARGE_DIMENSIONS = "249,6 × 101,2 × 60,6 мм"

TORQUE_SPECS: dict[int, _TorqueSpec] = {
    3: {
        "moment": "3 Нм",
        "damper-area": "до 0,3 м²",
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "< 35 с / возврат пружины < 20 с",
        "weight": "< 1,3 кг",
        "noise": ("макс. 55 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "> 50 мм",
        "dimensions": _SAFU_SMALL_DIMENSIONS,
    },
    10: {
        "moment": "10 Нм",
        "damper-area": "до 1,0 м²",
        "power": "15 Вт под нагрузкой / 3 Вт в режиме удержания",
        "running-time": "< 35 с / возврат пружины < 20 с",
        "weight": "< 2,5 кг",
        "noise": ("макс. 55 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины"),
        "shaft-length": "< 90 мм",
        "dimensions": _SAFU_LARGE_DIMENSIONS,
    },
}

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "Монтаж, подключение и настройка — по инструкции на карточке модели (серия SA..FQU, ускоренный ход).",
)


def parse_safqu_torque_nm(sku_code: str) -> int | None:
    """Extract rated torque from ``SA3FQU24-DS`` → ``3``."""
    match = _SAFQU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def safqu_sku_code(*, voltage: str, thermal: bool, torque_nm: int) -> str:
    """Build ``SA10FQU24-DST`` / ``SA3FQU230-DS``."""
    suffix = "DST" if thermal else "DS"
    return f"SA{torque_nm}FQU{voltage}-{suffix}"


def product_slug_for_nm(torque_nm: int) -> str:
    return f"privod-protivopozharniy-safqu-{torque_nm}nm"


def _product_title(torque_nm: int) -> str:
    return (
        f"SA{torque_nm}FQU | Электропривод противопожарного клапана "
        f"с пружинным возвратом (ускоренный ход), {torque_nm} Нм"
    )


def _sku_description(variant: SkuVariant, torque_nm: int, row: _TorqueSpec) -> str:
    lines = [
        (
            "Электропривод противопожарного клапана с пружинным возвратом (ускоренный ход). "
            f"Крутящий момент {row['moment']}, площадь заслонки {row['damper-area']}."
        ),
        f"Время поворота: {row['running-time']}.",
        "Управление: открыто/закрыто.",
        "Вспомогательные переключатели: 2 SPDT (исполнение -DS / -DST).",
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


def ensure_safqu_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """Create SA3FQU / SA10FQU products and four edition SKUs each when missing."""
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

        for voltage, thermal in (("24", False), ("24", True), ("230", False), ("230", True)):
            code = safqu_sku_code(voltage=voltage, thermal=thermal, torque_nm=torque_nm)
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
                slug=f"{p_slug}-{code.lower()}",
                sku_code=code,
                description="",
                is_published=False,
            )
            skus_created += 1

    return {
        "products_created": products_created,
        "skus_created": skus_created,
        "dry_run": dry_run,
    }


@cached_attributes
@transaction.atomic
def apply_safqu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    """Rewrite SA..FQU products/SKUs from fast fire/smoke manuals."""
    ensure = ensure_safqu_catalog(dry_run=dry_run)
    products = list(
        Product.objects.filter(
            skus__sku_code__iregex=r"(?i)^sa\d+fqu",
        ).distinct(),
    )
    skus_done = 0
    attrs = 0
    for product in products:
        skus = list(SKU.objects.filter(product=product, sku_code__iregex=r"(?i)^sa\d+fqu"))
        torque_nm = None
        for sku in skus:
            torque_nm = parse_safqu_torque_nm(sku.sku_code)
            if torque_nm is not None:
                break
        if torque_nm is None or torque_nm not in TORQUE_SPECS:
            continue
        spec = TORQUE_SPECS[torque_nm]
        title = _product_title(torque_nm)
        if not dry_run:
            write_copy(
                product,
                name=title[:300],
                description=SERIES_DESCRIPTION,
                instructions=SERIES_INSTRUCTIONS,
                specs_text="",
            )
        for sku in skus:
            nm = parse_safqu_torque_nm(sku.sku_code) or torque_nm
            row = TORQUE_SPECS.get(nm, spec)
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                write_copy(
                    sku,
                    name=title[:300],
                    description=_sku_description(variant, nm, row),
                    specs_text="",
                )
                clear_etl_attributes(sku)
            for name, slug, unit, value, _group in SHARED_ATTRS:
                if not dry_run:
                    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
                attrs += 1
            torque_rows = (
                ("Крутящий момент", "moment", "Нм", row["moment"]),
                ("Площадь заслонки", "damper-area", "м²", row["damper-area"]),
                ("Время поворота", "running-time", "с", row["running-time"]),
                ("Уровень шума", "noise", "дБ(A)", row["noise"]),
                ("Масса", "weight", "кг", row["weight"]),
                ("Габаритные размеры", "dimensions", "мм", row["dimensions"]),
                ("Длина вала заслонки", "shaft-length", "мм", row["shaft-length"]),
                ("Потребляемая мощность", "power-consumption", "", row["power"]),
            )
            for name, slug, unit, value in torque_rows:
                if not dry_run:
                    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
                attrs += 1
            if variant.voltage == "24":
                if not dry_run:
                    set_sku_attribute(
                        sku,
                        slug="voltage",
                        value="AC/DC 24 В, 50/60 Гц",
                        name="Номинальное напряжение",
                        unit="",
                    )
                    set_sku_attribute(
                        sku,
                        slug="protection-class",
                        value=PROTECTION_CLASS_III,
                        name="Класс защиты",
                        unit="",
                    )
                attrs += 2
            elif variant.voltage == "230":
                if not dry_run:
                    set_sku_attribute(
                        sku,
                        slug="voltage",
                        value="AC 100…240 В, 50/60 Гц",
                        name="Номинальное напряжение",
                        unit="",
                    )
                    set_sku_attribute(
                        sku,
                        slug="protection-class",
                        value=PROTECTION_CLASS_II,
                        name="Класс защиты",
                        unit="",
                    )
                attrs += 2
            skus_done += 1

    return {
        "products": len(products),
        "skus": skus_done,
        "attributes": attrs,
        "dry_run": dry_run,
        "ensure": ensure,
    }
