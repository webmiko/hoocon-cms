"""Canonical copy + ТТХ for Hoocon DA..FQU (fast spring-return damper actuators).

Source: English manual ``da10fqu-d_ds.pdf`` (factory EN drop 2026).
"""

from __future__ import annotations

import re
from typing import Any

from django.db import transaction

from catalog.etl.attr_write import cached_attributes, clear_etl_attributes, set_sku_attribute, write_copy
from catalog.etl.series_copy_dafu import SERIES_DESCRIPTION, SHARED_ATTRS, TORQUE_SPECS
from catalog.etl.sku_variant import SkuVariant, parse_sku_variant
from catalog.etl.tech_copy import PROTECTION_CLASS_II, PROTECTION_CLASS_III, normalize_tech_copy
from catalog.models import SKU, Category, Product

_DAFQU_CODE = re.compile(r"(?i)^da(?P<nm>\d+)fqu")

CATEGORY_SLUG = "elektroprivody-s-pruzhinnym-vozvratom"

_ON_OFF_SPEC: dict[str, str] = {
    "running-time": "< 35 с / возврат пружины < 20 с",
    "power": "15 Вт под нагрузкой / 3 Вт в режиме удержания",
    "weight": "< 2,6 кг",
    "shaft-length": "> 90 мм",
    "shaft-diameter": "круглый 10…21 мм, квадратный 9×9…15×15 мм",
    "noise": "макс. 45 дБ(А) при работе двигателя, макс. 62 дБ(А) при возврате пружины",
}

TORQUE_NMS: tuple[int, ...] = (10,)

SERIES_INSTRUCTIONS = normalize_tech_copy(
    "Монтаж, подключение и настройка — по инструкции на карточке модели (серия DA..FQU, ускоренный ход).",
)


def parse_dafqu_torque_nm(sku_code: str) -> int | None:
    match = _DAFQU_CODE.match((sku_code or "").strip().replace(" ", ""))
    if match is None:
        return None
    return int(match.group("nm"))


def dafqu_sku_code(*, voltage: str, aux: bool, torque_nm: int) -> str:
    suffix = "DS" if aux else "D"
    return f"DA{torque_nm}FQU{voltage}-{suffix}"


def product_slug_for_nm(torque_nm: int) -> str:
    return f"privod-vozdushniy-pruzhina-dafqu-{torque_nm}nm"


def _product_title(torque_nm: int) -> str:
    return f"DA{torque_nm}FQU | Электропривод с пружинным возвратом (ускоренный ход), {torque_nm} Нм"


def _row_for_nm(torque_nm: int) -> dict[str, str] | None:
    base = TORQUE_SPECS.get(torque_nm)
    if base is None:
        return None
    return {**base, **_ON_OFF_SPEC}


def _sku_description(variant: SkuVariant, row: dict[str, str]) -> str:
    lines = [
        (
            "Электропривод с пружинным возвратом (ускоренный ход). "
            f"Крутящий момент {row['moment']}, площадь заслонки {row['damper-area']}."
        ),
        f"Время поворота: {row['running-time']}.",
        "Управление: открыто/закрыто.",
    ]
    if variant.aux_switch:
        lines.append("Вспомогательные переключатели: 2 SPDT (исполнение -DS).")
    if variant.voltage == "24":
        lines.append("Номинальное напряжение: AC/DC 24 В, 50/60 Гц.")
    elif variant.voltage == "230":
        lines.append("Номинальное напряжение: AC 100…240 В, 50/60 Гц.")
    return normalize_tech_copy("\n".join(lines))


def ensure_dafqu_catalog(*, dry_run: bool = False) -> dict[str, Any]:
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
    for torque_nm in TORQUE_NMS:
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

        for voltage, aux in (("24", False), ("24", True), ("230", False), ("230", True)):
            code = dafqu_sku_code(voltage=voltage, aux=aux, torque_nm=torque_nm)
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
def apply_dafqu_enrichment(*, dry_run: bool = False) -> dict[str, Any]:
    ensure = ensure_dafqu_catalog(dry_run=dry_run)
    products = list(
        Product.objects.filter(skus__sku_code__iregex=r"(?i)^da\d+fqu").distinct(),
    )
    skus_done = 0
    attrs = 0
    for product in products:
        skus = list(SKU.objects.filter(product=product, sku_code__iregex=r"(?i)^da\d+fqu"))
        torque_nm = None
        for sku in skus:
            torque_nm = parse_dafqu_torque_nm(sku.sku_code)
            if torque_nm is not None:
                break
        row = _row_for_nm(torque_nm or 0)
        if row is None:
            continue
        title = _product_title(torque_nm or 10)
        if not dry_run:
            write_copy(
                product,
                name=title[:300],
                description=SERIES_DESCRIPTION,
                instructions=SERIES_INSTRUCTIONS,
                specs_text="",
            )
        for sku in skus:
            variant = parse_sku_variant(sku.sku_code)
            if not dry_run:
                write_copy(
                    sku,
                    name=title[:300],
                    description=_sku_description(variant, row),
                    specs_text="",
                )
                clear_etl_attributes(sku)
            for name, slug, unit, value, _group in SHARED_ATTRS:
                if not dry_run:
                    set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
                attrs += 1
            for name, slug, unit, value in (
                ("Крутящий момент", "moment", "Нм", row["moment"]),
                ("Площадь заслонки", "damper-area", "м²", row["damper-area"]),
                ("Время поворота", "running-time", "с", row["running-time"]),
                ("Потребляемая мощность", "power-consumption", "", row["power"]),
                ("Масса", "weight", "кг", row["weight"]),
                ("Габаритные размеры", "dimensions", "мм", row["dimensions"]),
                ("Длина вала заслонки", "shaft-length", "мм", row["shaft-length"]),
                ("Диаметр вала заслонки", "shaft-diameter", "мм", row["shaft-diameter"]),
                ("Уровень шума", "noise", "дБ(A)", row["noise"]),
                ("Трансформатор", "transformer-va", "В·А", row["transformer-va"]),
            ):
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
