"""Seed HVD-Q and HV*QX (capacitor) from the 2025 catalog.

Creates Products/SKUs missing on the site, upserts ТТХ from datasheets /
catalog pages, and optionally attaches local HV-seria photos.

HVA-P (spring) is out of RF scope — Chinese-market only; do not seed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.db import transaction

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.manual_diagrams import SORT_WIRING
from catalog.etl.manual_pdfs import attach_hva_manuals, default_manuals_dir
from catalog.etl.sku_instructions import damper_area_for_nm
from catalog.etl.tech_copy import (
    CONTROL_MODULATING,
    CONTROL_ON_OFF,
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
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, Category, Product, ProductImage

CATEGORY_AIR = "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
CATEGORY_QX = "elektronnye-otkazoustoychivye-vozdushnye-privody"

SORT_PRODUCT: Final[int] = 0
SORT_LOCAL_DIMENSIONS: Final[int] = 6

_EDITIONS: Final[tuple[tuple[str, bool], ...]] = (
    ("24", False),
    ("24", True),
    ("230", False),
    ("230", True),
)

# HVD fast Q on/off — catalog pp. 47–54 (40Q already on site).
HVD_Q_NMS: Final[tuple[int, ...]] = (5, 10, 20, 40)

# Capacitor fail-safe — catalog pp. 60–67 (HVD on/off + HVA modulating).
QX_NMS: Final[tuple[int, ...]] = (5, 10, 20, 40)

AttrRow = tuple[str, str, str, str]

_SHARED_BASE: Final[tuple[AttrRow, ...]] = (
    ("Ручное управление", "manual-override", "", MANUAL_OVERRIDE_BUTTON_SELF_RESET),
    ("Индикация положения", "position-indication", "", "механическая"),
    ("Степень защиты", "ip-rating", "", "IP54"),
    ("Температура окружающей среды", "ambient-temp", "°C", "-20...+50 °C"),
    ("Влажность", "humidity", "", "95 % RH, без конденсации"),
    ("Сечение провода", "wire-cross-section", "мм²", "0,5 мм²"),
)

HVD_Q_SPECS: Final[dict[int, dict[str, str]]] = {
    5: {
        "moment": "5 Нм",
        "damper-area": damper_area_for_nm(5),
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 50 мм",
        "dimensions": "144,1 × 71,1 × 62,1 мм",
        "weight": "< 0,8 кг",
        "power": "3,5 Вт / 0,5 Вт (удержание)",
        "transformer-va": "8 ВА",
    },
    10: {
        "moment": "10 Нм",
        "damper-area": damper_area_for_nm(10),
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 80 мм",
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
        "power": "9 Вт / 0,5 Вт (удержание)",
        "transformer-va": "12 ВА",
    },
    20: {
        "moment": "20 Нм",
        "damper-area": damper_area_for_nm(20),
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "191,8 × 103,4 × 68 мм",
        "weight": "< 1,4 кг",
        "power": "8 Вт / 0,5 Вт (удержание)",
        "transformer-va": "18 ВА",
    },
    40: {
        "moment": "40 Нм",
        "damper-area": damper_area_for_nm(40),
        "running-time": "< 20 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "198,6 × 110,2 × 68 мм",
        "weight": "< 1,5 кг",
        "power": "15 Вт / 3 Вт (удержание)",
        "transformer-va": "50 ВА",
    },
}

# Shared body per Nm for capacitor QX (HVD on/off + HVA modulating).
QX_SPECS: Final[dict[int, dict[str, str]]] = {
    5: {
        "moment": "5 Нм",
        "damper-area": damper_area_for_nm(5),
        "running-time": "< 20 с",
        "failsafe-time": "< 30 с",
        "charge-time": "3 мин 30 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
        "power": "9 Вт / 1 Вт (удержание)",
        "transformer-va": "25 ВА",
    },
    10: {
        "moment": "10 Нм",
        "damper-area": damper_area_for_nm(10),
        "running-time": "< 20 с",
        "failsafe-time": "< 30 с",
        "charge-time": "3 мин 30 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "167,8 × 86,2 × 68 мм",
        "weight": "< 1,1 кг",
        "power": "11 Вт / 1 Вт (удержание)",
        "transformer-va": "30 ВА",
    },
    20: {
        "moment": "20 Нм",
        "damper-area": damper_area_for_nm(20),
        "running-time": "< 20 с",
        "failsafe-time": "< 30 с",
        "charge-time": "3 мин 30 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "191,8 × 103,4 × 68 мм",
        "weight": "< 1,4 кг",
        "power": "8 Вт / 1 Вт (удержание)",
        "transformer-va": "35 ВА",
    },
    40: {
        "moment": "40 Нм",
        "damper-area": damper_area_for_nm(40),
        "running-time": "< 20 с",
        "failsafe-time": "< 30 с",
        "charge-time": "7 мин 30 с",
        "noise": "55 дБ",
        "shaft-length": "≥ 60 мм",
        "dimensions": "198,6 × 110,2 × 68 мм",
        "weight": "< 1,5 кг",
        "power": "15 Вт / 3 Вт (удержание)",
        "transformer-va": "60 ВА",
    },
}

_SERIES_INSTRUCTIONS = normalize_tech_copy(
    "\n".join(
        [
            "Монтаж и подключение — по инструкции на карточке модели.",
            "",
            *MANUAL_SAFETY_ATTENTION_LINES,
        ],
    ),
)

_PHOTO_ROOTS: Final[tuple[Path, ...]] = (
    Path.home() / "Yandex.Disk.localized/фото для сайта/архив/foto/HV seria",
    Path.home() / "Yandex.Disk.localized/фото для сайта/архив/продукция фото/HV seria",
)


def _photo_root() -> Path | None:
    for root in _PHOTO_ROOTS:
        if root.is_dir():
            return root
    return None


def _hvd_q_code(*, voltage: str, aux: bool, nm: int) -> str:
    return f"HVD{voltage}{'S' if aux else ''}-{nm}Q"


def _qx_code(*, brand: str, voltage: str, aux: bool, nm: int) -> str:
    return f"{brand}{voltage}{'S' if aux else ''}-{nm}QX"


def product_slug_hvd_q(nm: int) -> str:
    return f"privod-vozdushniy-hvd-{nm}q"


def product_slug_qx(*, brand: str, nm: int) -> str:
    letter = brand.lower()
    return f"privod-vozdushniy-kondensator-{letter}-{nm}qx"


def _set_voltage_attrs(sku: SKU, voltage: str) -> int:
    n = 0
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
    n += 2
    return n


def _upsert_image(
    sku: SKU,
    *,
    kind: str,
    raw: bytes,
    alt: str,
    sort_order: int,
    source_url: str,
    dry_run: bool,
) -> str:
    webp = convert_bytes_to_webp(raw, quality=90, max_edge=1600)
    existing = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if dry_run:
        return "update" if existing else "create"
    filename = f"{sku.sku_code.lower()}-{kind}.webp"
    with transaction.atomic():
        if existing is None:
            image = ProductImage(
                sku=sku,
                alt=alt[:300],
                source_url=source_url,
                sort_order=sort_order,
                is_published=True,
            )
            image.image.save(filename, ContentFile(webp), save=False)
            image.full_clean()
            image.save()
            return "create"
        existing.alt = alt[:300]
        existing.sort_order = sort_order
        existing.is_published = True
        existing.image.save(filename, ContentFile(webp), save=False)
        existing.full_clean()
        existing.save()
        return "update"


def _attach_hvd_folder_media(
    sku: SKU,
    *,
    nm: int,
    fast_q: bool,
    dry_run: bool,
) -> dict[str, int]:
    root = _photo_root()
    counts = {"created": 0, "updated": 0}
    if root is None:
        return counts
    folder = root / f"hvd-{nm}"
    if not folder.is_dir():
        return counts
    label = f"HVD-{nm}{'Q' if fast_q else ''}"
    product_candidates: list[Path] = []
    dim_candidates: list[Path] = []
    for name in (
        f"hvd-{nm}q.webp",
        f"hvd-{nm}.webp",
        "hvd-40q.webp",
        f"hvd-{nm}-foto.webp",
        f"hvd-{nm}.jpg",
        f"hvd-{nm}.png",
    ):
        product_candidates.append(folder / name)
    for name in (
        f"hvd-{nm}-razmer.webp",
        f"hvd-{nm} razmer.webp",
        f"hvd-{nm}-razmeri.webp",
        "hvd40-razmer.webp",
        f"hvd-{nm} razmer.png",
        "hvd40-razmer.png",
    ):
        dim_candidates.append(folder / name)

    from catalog.etl.hva_local_media import _best_raster

    product = _best_raster(product_candidates, min_edge=600)
    dims = _best_raster(dim_candidates, min_edge=400)
    wiring = None
    for name in ("hvd-cxema-on-off.webp", f"hvd-{nm}-cxema.webp", "hvd-5-cxema.webp"):
        for base in (folder, root / "hvd-5", root / "hvd-10"):
            candidate = base / name
            if candidate.is_file():
                wiring = candidate
                break
        if wiring:
            break
    jobs = [
        ("product", f"{label} | фото привода", SORT_PRODUCT, product),
        ("dimensions", f"{label} | Габаритные размеры (мм)", SORT_LOCAL_DIMENSIONS, dims),
        ("wiring", f"{label} | Схема подключения", SORT_WIRING, wiring),
    ]
    for kind, alt, sort_order, path in jobs:
        if path is None or not path.is_file():
            continue
        url = f"https://hoocon.ru/.local-assets/hvd-catalog/hvd{nm}{'q' if fast_q else ''}-{kind}.webp"
        action = _upsert_image(
            sku,
            kind=kind,
            raw=path.read_bytes(),
            alt=alt,
            sort_order=sort_order,
            source_url=url,
            dry_run=dry_run,
        )
        if action == "create":
            counts["created"] += 1
        elif action == "update":
            counts["updated"] += 1
    return counts


def ensure_hvd_q_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """Create missing HVD-*Q products (5/10/20/40) and four on/off editions."""
    category = Category.objects.filter(slug=CATEGORY_AIR).first()
    if category is None:
        return {"products_created": 0, "skus_created": 0, "error": f"missing {CATEGORY_AIR}"}
    products_created = 0
    skus_created = 0
    for nm in HVD_Q_NMS:
        p_slug = product_slug_hvd_q(nm)
        title = f"HVD-{nm}Q | {nm} Нм Привод воздушный без возвратной пружины ускоренный позиционное управление"
        product = Product.objects.filter(slug=p_slug).first()
        if product is None:
            if dry_run:
                products_created += 1
            else:
                product = Product.objects.create(
                    category=category,
                    name=title[:200],
                    slug=p_slug,
                    description=normalize_tech_copy(
                        "Ускоренные электроприводы HVD-Q — открыто/закрыто, "
                        "2-/3-позиционное управление без возвратной пружины.",
                    ),
                    instructions=_SERIES_INSTRUCTIONS,
                )
                products_created += 1
        for voltage, aux in _EDITIONS:
            code = _hvd_q_code(voltage=voltage, aux=aux, nm=nm)
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
                is_published=True,
            )
            skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created, "dry_run": dry_run}


def ensure_hv_qx_catalog(*, dry_run: bool = False) -> dict[str, Any]:
    """Create HVD/HVA *QX capacitor products for 5/10/20/40 Nm."""
    category = Category.objects.filter(slug=CATEGORY_QX).first()
    if category is None:
        return {"products_created": 0, "skus_created": 0, "error": f"missing {CATEGORY_QX}"}
    products_created = 0
    skus_created = 0
    for brand, control_label in (("HVD", "открыто/закрыто"), ("HVA", "пропорциональное")):
        for nm in QX_NMS:
            p_slug = product_slug_qx(brand=brand, nm=nm)
            title = (
                f"{brand}-{nm}QX | {nm} Нм Привод воздушный быстродействующий "
                f"со встроенным конденсатором, {control_label} управление"
            )
            product = Product.objects.filter(slug=p_slug).first()
            if product is None:
                if dry_run:
                    products_created += 1
                else:
                    product = Product.objects.create(
                        category=category,
                        name=title[:200],
                        slug=p_slug,
                        description=normalize_tech_copy(
                            "Быстродействующие приводы со встроенным конденсатором: "
                            "возврат при пропадании питания без механической пружины.",
                        ),
                        instructions=_SERIES_INSTRUCTIONS,
                    )
                    products_created += 1
            for voltage, aux in _EDITIONS:
                code = _qx_code(brand=brand, voltage=voltage, aux=aux, nm=nm)
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
                    is_published=True,
                )
                skus_created += 1
    return {"products_created": products_created, "skus_created": skus_created, "dry_run": dry_run}


def _enrich_hvd_q_sku(sku: SKU, nm: int, voltage: str, aux: bool, *, dry_run: bool) -> int:
    row = HVD_Q_SPECS[nm]
    if dry_run:
        return 0
    attrs = 0
    set_sku_attribute(sku, slug="control", value=CONTROL_ON_OFF, name="Управление", unit="")
    attrs += 1
    for name, slug, unit, value in _SHARED_BASE:
        set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
        attrs += 1
    for name, slug, unit, key in (
        ("Крутящий момент", "moment", "Нм", "moment"),
        ("Площадь заслонки", "damper-area", "м²", "damper-area"),
        ("Время поворота", "running-time", "с", "running-time"),
        ("Уровень шума", "noise", "дБ", "noise"),
        ("Длина вала заслонки", "shaft-length", "мм", "shaft-length"),
        ("Габаритные размеры", "dimensions", "мм", "dimensions"),
        ("Масса", "weight", "кг", "weight"),
        ("Потребляемая мощность", "power-consumption", "Вт", "power"),
        ("Мощность трансформатора", "transformer-va", "ВА", "transformer-va"),
    ):
        set_sku_attribute(sku, slug=slug, value=row[key], name=name, unit=unit)
        attrs += 1
    attrs += _set_voltage_attrs(sku, voltage)
    if aux:
        set_sku_attribute(
            sku,
            slug="aux-switch",
            value="SPDT-2",
            name="Вспомогательный переключатель",
            unit="",
        )
        attrs += 1
    return attrs


def _enrich_qx_sku(
    sku: SKU,
    *,
    brand: str,
    nm: int,
    voltage: str,
    aux: bool,
    dry_run: bool,
) -> int:
    row = QX_SPECS[nm]
    if dry_run:
        return 0
    attrs = 0
    if brand == "HVA":
        set_sku_attribute(sku, slug="control", value=CONTROL_MODULATING, name="Управление", unit="")
        set_sku_attribute(
            sku,
            slug=CONTROL_SIGNAL_Y_SLUG,
            value=CONTROL_SIGNAL_Y_CANON,
            name=CONTROL_SIGNAL_Y_LABEL,
            unit="",
        )
        set_sku_attribute(
            sku,
            slug=FEEDBACK_SIGNAL_U_SLUG,
            value=FEEDBACK_SIGNAL_U_CANON,
            name=FEEDBACK_SIGNAL_U_LABEL,
            unit="",
        )
        attrs += 3
    else:
        set_sku_attribute(sku, slug="control", value=CONTROL_ON_OFF, name="Управление", unit="")
        attrs += 1
    for name, slug, unit, value in _SHARED_BASE:
        set_sku_attribute(sku, slug=slug, value=value, name=name, unit=unit)
        attrs += 1
    for name, slug, unit, key in (
        ("Крутящий момент", "moment", "Нм", "moment"),
        ("Площадь заслонки", "damper-area", "м²", "damper-area"),
        ("Время поворота", "running-time", "с", "running-time"),
        ("Время возврата без питания", "failsafe-time", "с", "failsafe-time"),
        ("Время зарядки конденсатора", "charge-time", "с", "charge-time"),
        ("Уровень шума", "noise", "дБ", "noise"),
        ("Длина вала заслонки", "shaft-length", "мм", "shaft-length"),
        ("Габаритные размеры", "dimensions", "мм", "dimensions"),
        ("Масса", "weight", "кг", "weight"),
        ("Потребляемая мощность", "power-consumption", "Вт", "power"),
        ("Мощность трансформатора", "transformer-va", "ВА", "transformer-va"),
    ):
        set_sku_attribute(sku, slug=slug, value=row[key], name=name, unit=unit)
        attrs += 1
    attrs += _set_voltage_attrs(sku, voltage)
    # Capacitor bodies are Class II even on 24 V in the catalog table.
    set_sku_attribute(
        sku,
        slug="protection-class",
        value="II (полная изоляция)",
        name="Класс защиты",
        unit="",
    )
    if aux:
        set_sku_attribute(
            sku,
            slug="aux-switch",
            value="SPDT-2",
            name="Вспомогательный переключатель",
            unit="",
        )
        attrs += 1
    return attrs


_HVD_Q_RE = re.compile(r"(?i)^hvd(?P<volt>24|230)(?P<aux>s)?-(?P<nm>\d+)q$")
_QX_RE = re.compile(r"(?i)^(?P<brand>hva|hvd)(?P<volt>24|230)(?P<aux>s)?-(?P<nm>\d+)qx$")


def apply_hv_extra_enrichment(*, dry_run: bool = False, with_media: bool = False) -> dict[str, Any]:
    """Ensure + enrich HVD-Q and HV*QX families (HVA-P is out of RF scope)."""
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "ensure_hvd_q": ensure_hvd_q_catalog(dry_run=dry_run),
        "ensure_qx": ensure_hv_qx_catalog(dry_run=dry_run),
        "skus": 0,
        "attributes": 0,
        "media_created": 0,
        "media_updated": 0,
        "errors": [],
    }
    for key in ("ensure_hvd_q", "ensure_qx"):
        err = summary[key].get("error")
        if err:
            summary["errors"].append(err)

    for sku in SKU.objects.filter(
        sku_code__iregex=r"(?i)^(hvd|hva)(24|230)s?-\d+(q|qx)$",
    ).order_by("sku_code"):
        code = sku.sku_code
        m_q = _HVD_Q_RE.match(code)
        m_qx = _QX_RE.match(code)
        if m_q:
            nm = int(m_q.group("nm"))
            if nm not in HVD_Q_SPECS:
                continue
            summary["attributes"] += _enrich_hvd_q_sku(
                sku,
                nm,
                m_q.group("volt"),
                bool(m_q.group("aux")),
                dry_run=dry_run,
            )
            summary["skus"] += 1
            if with_media:
                media = _attach_hvd_folder_media(sku, nm=nm, fast_q=True, dry_run=dry_run)
                summary["media_created"] += media.get("created", 0)
                summary["media_updated"] += media.get("updated", 0)
        elif m_qx:
            nm = int(m_qx.group("nm"))
            if nm not in QX_SPECS:
                continue
            brand = m_qx.group("brand").upper()
            summary["attributes"] += _enrich_qx_sku(
                sku,
                brand=brand,
                nm=nm,
                voltage=m_qx.group("volt"),
                aux=bool(m_qx.group("aux")),
                dry_run=dry_run,
            )
            summary["skus"] += 1
            if with_media and brand == "HVD":
                media = _attach_hvd_folder_media(sku, nm=nm, fast_q=True, dry_run=dry_run)
                summary["media_created"] += media.get("created", 0)
                summary["media_updated"] += media.get("updated", 0)

    manuals = attach_hva_manuals(default_manuals_dir(), dry_run=dry_run)
    summary["manuals"] = {
        "created": manuals.get("created", 0),
        "updated": manuals.get("updated", 0),
        "skipped": manuals.get("skipped", 0),
        "warnings": manuals.get("warnings") or [],
    }
    if with_media:
        from catalog.etl.hva_local_media import apply_hva_local_media

        # QX reuse std family body shots when no dedicated pack exists.
        hva_media = apply_hva_local_media(dry_run=dry_run)
        summary["media_created"] += hva_media.get("created", 0)
        summary["media_updated"] += hva_media.get("updated", 0)
    return summary
