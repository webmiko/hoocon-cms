"""HVD-3P / HVD-5P air spring-return cards from the Russian manuals.

Four editions per torque: ``HVD24-3P``, ``HVD24S-3P``, ``HVD230-3P``, ``HVD230S-3P``
(and the same for 5 Нм). Specs are the RU instruction tables, not the EN P-series.
New SKUs stay unpublished until stock is known.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile

from catalog.etl.attr_write import clear_etl_attributes, set_sku_attribute, write_copy
from catalog.etl.image_upsert import upsert_sku_image
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.tech_copy import (
    CONTROL_ON_OFF,
    MANUAL_OVERRIDE_BUTTON_SELF_RESET,
    PROTECTION_CLASS_II,
    PROTECTION_CLASS_III,
)
from catalog.etl.webp import DEFAULT_WEBP_QUALITY, MAX_EDGE_PX, convert_bytes_to_webp
from catalog.facets.aux import normalize_aux_switch_value
from catalog.facets.temp_sensor import TEMP_SENSOR_NONE
from catalog.models import SKU, Category, Product, ProductFile, ProductImage

logger = logging.getLogger(__name__)

CATEGORY_SLUG = "elektroprivody-s-pruzhinnym-vozvratom"
_SOURCE = "https://hoocon.ru/.local-assets/manuals-ru/hvd-{nm}p-{kind}.webp"

# RU manuals HVD-3P / HVD-5P (tables + dimension drawings).
TORQUE_SPECS: dict[int, dict[str, str]] = {
    3: {
        "moment": "3",
        "damper-area": "до 0,3",
        "running-time": "< 75 с / возврат пружины < 25 с",
        "power": "5 Вт под нагрузкой / 2 Вт в режиме удержания",
        "shaft-diameter": "круглый 10…16 мм, квадратный 7×7…11×11 мм",
        "weight": "< 1,3",
        "dimensions": "132 × 68,5 × 59",
    },
    5: {
        "moment": "5",
        "damper-area": "до 0,5",
        "running-time": "< 70 с / возврат пружины < 20 с",
        "power": "5 Вт под нагрузкой / 3 Вт в режиме удержания",
        "shaft-diameter": "круглый 10…16 мм, квадратный 8×8…11×11 мм",
        "weight": "< 1,8",
        "dimensions": "158 × 102 × 59",
    },
}

_SHARED: tuple[tuple[str, str, str, str], ...] = (
    ("Сечение провода", "wire-cross-section", "мм²", "0,5"),
    ("Степень защиты", "ip-rating", "", "IP54"),
    ("Температура окружающей среды", "ambient-temp", "°C", "–20…+50"),
    ("Температура хранения", "storage-temp", "°C", "–40…+70"),
    ("Влажность", "humidity", "", "5…95 % относительной влажности, без конденсата"),
    ("Угол поворота", "rotation-angle", "°", "макс. 95"),
    (
        "Уровень шума",
        "noise",
        "дБ(А)",
        "макс. 45 при работе двигателя, макс. 62 при возврате пружины",
    ),
    ("Индикация положения", "position-indication", "", "Механический указатель"),
    ("Длина вала заслонки", "shaft-length", "мм", "> 90"),
    (
        "Направление вращения",
        "rotation-direction",
        "",
        "для монтажа с противоположной стороны",
    ),
    ("Ручное управление", "manual-override", "", MANUAL_OVERRIDE_BUTTON_SELF_RESET),
    ("Датчик температуры", "temp-sensor", "", TEMP_SENSOR_NONE),
)

_VOLTAGE = {
    "24": ("AC/DC 24 В, 50/60 Гц", PROTECTION_CLASS_III),
    "230": ("AC 100…240 В, 50/60 Гц", PROTECTION_CLASS_II),
}

_DIAGRAMS: tuple[tuple[str, str, int, str], ...] = (
    ("wiring.png", "wiring", 5, "Схема подключения из инструкции"),
    ("dimensions.png", "dimensions", 8, "Габаритные размеры привода (мм), чертёж из инструкции"),
    ("rotation.png", "rotation", 3, "Направление вращения"),
    ("thermal.png", "angle-stop", 6, "Механический упор угла"),
)


def product_slug_for_nm(torque_nm: int) -> str:
    """One catalog tile per torque."""
    return f"privod-vozdushniy-pruzhina-hvd-{torque_nm}p"


def hvdp_sku_code(*, voltage: str, aux: bool, torque_nm: int) -> str:
    """``HVD24S-3P`` / ``HVD230-5P``."""
    mark = "S" if aux else ""
    return f"HVD{voltage}{mark}-{torque_nm}P"


def default_assets_root() -> Path:
    """``_manuals-ru/HV/assets``."""
    return Path(__file__).resolve().parents[3] / "_manuals-ru" / "HV" / "assets"


def default_pdf_root() -> Path:
    """``_инструкции-pdf/RU``."""
    return Path(__file__).resolve().parents[3] / "_инструкции-pdf" / "RU"


def _title(torque_nm: int) -> str:
    return f"HVD-{torque_nm}P | {torque_nm} Нм Привод воздушный с возвратной пружиной"


def _description(torque_nm: int, spec: dict[str, str]) -> str:
    return (
        "Электропривод воздушной заслонки с возвратной пружиной. "
        f"Крутящий момент {spec['moment']} Нм, площадь заслонки {spec['damper-area']} м². "
        f"Время поворота: {spec['running-time']}."
    )


def apply_hvdp_enrichment(
    *,
    dry_run: bool = False,
    assets_root: Path | None = None,
    pdf_root: Path | None = None,
) -> dict[str, Any]:
    """Create HVD-3P/5P products and fill ТТХ, photos and the RU PDF.

    Returns:
        Counters plus ``missing`` when a manual file is absent.
    """
    assets = assets_root if assets_root is not None else default_assets_root()
    pdfs = pdf_root if pdf_root is not None else default_pdf_root()
    summary: dict[str, Any] = {
        "products_created": 0,
        "skus_created": 0,
        "attributes": 0,
        "images": 0,
        "pdfs": 0,
        "missing": [],
        "dry_run": dry_run,
    }
    category = Category.objects.filter(slug=CATEGORY_SLUG).first()
    if category is None:
        summary["error"] = f"category missing: {CATEGORY_SLUG}"
        return summary

    for torque_nm, spec in TORQUE_SPECS.items():
        product = _ensure_product(category, torque_nm, spec, summary, dry_run=dry_run)
        for voltage in ("24", "230"):
            for aux in (False, True):
                code = hvdp_sku_code(voltage=voltage, aux=aux, torque_nm=torque_nm)
                sku = _ensure_sku(product, code, torque_nm, summary, dry_run=dry_run)
                if sku is None:
                    continue
                summary["attributes"] += _write_attrs(sku, spec, dry_run=dry_run)
                summary["images"] += _attach_images(
                    sku,
                    torque_nm=torque_nm,
                    aux=aux,
                    assets=assets,
                    summary=summary,
                    dry_run=dry_run,
                )
                if _attach_pdf(sku, torque_nm, pdfs, dry_run=dry_run):
                    summary["pdfs"] += 1
    return summary


def _ensure_product(
    category: Category,
    torque_nm: int,
    spec: dict[str, str],
    summary: dict[str, Any],
    *,
    dry_run: bool,
) -> Product | None:
    slug = product_slug_for_nm(torque_nm)
    product = Product.objects.filter(slug=slug).first()
    title = _title(torque_nm)
    if product is None:
        summary["products_created"] += 1
        if dry_run:
            return None
        product = Product.objects.create(
            category=category,
            name=title[:200],
            slug=slug,
            description=_description(torque_nm, spec),
        )
        return product
    if not dry_run:
        write_copy(
            product,
            name=title[:200],
            description=_description(torque_nm, spec),
            category=category,
        )
    return product


def _ensure_sku(
    product: Product | None,
    code: str,
    torque_nm: int,
    summary: dict[str, Any],
    *,
    dry_run: bool,
) -> SKU | None:
    sku = SKU.objects.filter(sku_code__iexact=code).first()
    title = _title(torque_nm)
    if sku is None:
        summary["skus_created"] += 1
        if dry_run or product is None:
            return None
        return SKU.objects.create(
            product=product,
            name=title[:300],
            slug=f"{product_slug_for_nm(torque_nm)}-{code.lower()}",
            sku_code=code,
            description=_description(torque_nm, TORQUE_SPECS[torque_nm]),
            is_published=False,
        )
    if not dry_run:
        write_copy(sku, name=title[:300], description=_description(torque_nm, TORQUE_SPECS[torque_nm]))
    return sku


def _write_attrs(sku: SKU, spec: dict[str, str], *, dry_run: bool) -> int:
    variant = parse_sku_variant(sku.sku_code)
    rows: list[tuple[str, str, str, str]] = list(_SHARED)
    rows.extend(
        (
            ("Крутящий момент", "moment", "Нм", spec["moment"]),
            ("Площадь заслонки", "damper-area", "м²", spec["damper-area"]),
            ("Время поворота", "running-time", "", spec["running-time"]),
            ("Потребляемая мощность", "power-consumption", "", spec["power"]),
            ("Диаметр вала", "shaft-diameter", "", spec["shaft-diameter"]),
            ("Масса", "weight", "кг", spec["weight"]),
            ("Габаритные размеры", "dimensions", "мм", spec["dimensions"]),
            ("Управление", "control", "", CONTROL_ON_OFF),
            ("Вспомогательный переключатель", "aux-switch", "", normalize_aux_switch_value("", sku_code=sku.sku_code)),
        ),
    )
    voltage, protection = _VOLTAGE[variant.voltage or "24"]
    rows.append(("Номинальное напряжение", "voltage", "", voltage))
    rows.append(("Класс защиты", "protection-class", "", protection))
    if dry_run:
        return len(rows)
    clear_etl_attributes(sku)
    for name, slug, unit, value in rows:
        set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
    return len(rows)


def _attach_images(
    sku: SKU,
    *,
    torque_nm: int,
    aux: bool,
    assets: Path,
    summary: dict[str, Any],
    dry_run: bool,
) -> int:
    folder = assets / f"hvd-{torque_nm}p"
    written = 0
    product_png = folder / "product.png"
    if not product_png.is_file():
        summary["missing"].append(f"{sku.sku_code}:product")
    else:
        written += _upsert_png(
            sku,
            path=product_png,
            kind="product",
            torque_nm=torque_nm,
            alt=f"{sku.sku_code} | фото привода",
            sort_order=0,
            dry_run=dry_run,
        )
    for filename, kind, sort_order, caption in _DIAGRAMS:
        path = folder / filename
        if not path.is_file():
            summary["missing"].append(f"{sku.sku_code}:{kind}")
            continue
        written += _upsert_png(
            sku,
            path=path,
            kind=kind,
            torque_nm=torque_nm,
            alt=f"{sku.sku_code} | {caption}",
            sort_order=sort_order,
            dry_run=dry_run,
        )
    aux_path = folder / "aux-diagram.png"
    if aux and aux_path.is_file():
        written += _upsert_png(
            sku,
            path=aux_path,
            kind="aux",
            torque_nm=torque_nm,
            alt=f"{sku.sku_code} | Вспомогательные переключатели",
            sort_order=7,
            dry_run=dry_run,
        )
    if not dry_run:
        _hide_angle_stop_as_thermal(sku)
    return written


def _upsert_png(
    sku: SKU,
    *,
    path: Path,
    kind: str,
    torque_nm: int,
    alt: str,
    sort_order: int,
    dry_run: bool,
) -> int:
    webp = b""
    if not dry_run:
        webp = convert_bytes_to_webp(
            path.read_bytes(),
            quality=DEFAULT_WEBP_QUALITY,
            max_edge=MAX_EDGE_PX,
        )
    action, _image = upsert_sku_image(
        sku,
        source_url=_SOURCE.format(nm=torque_nm, kind=kind),
        filename=f"{sku.sku_code.lower()}-{kind}.webp",
        webp=webp,
        alt=alt,
        sort_order=sort_order,
        dry_run=dry_run,
    )
    return 1 if action in {"create", "update"} else 0


def _hide_angle_stop_as_thermal(sku: SKU) -> None:
    """``thermal.png`` in the HVD-P manual is the angle stop, not a SAF72 photo."""
    ProductImage.objects.filter(sku=sku, source_url__icontains="hvd-", alt__icontains="SAF72").update(
        is_published=False,
    )


def _attach_pdf(sku: SKU, torque_nm: int, pdf_root: Path, *, dry_run: bool) -> bool:
    path = pdf_root / f"HVD-{torque_nm}P.pdf"
    title = f"Инструкция HVD-{torque_nm}P"
    if not path.is_file():
        return False
    if ProductFile.objects.filter(sku=sku, title=title).exists():
        return False
    if dry_run:
        return True
    payload = path.read_bytes()
    if not payload.startswith(b"%PDF"):
        logger.warning("hvdp skip non-pdf %s", path)
        return False
    row = ProductFile(
        sku=sku,
        title=title,
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=0,
    )
    row.file.save(f"{sku.sku_code.lower()}-manual.pdf", ContentFile(payload), save=True)
    return True
