"""Ensure Products/SKUs missing vs 2022 Russian AI albums in media-webp.

Local-only sources (not committed)::

    ~/Yandex.Disk.localized/фото для сайта/media-webp/
        浒江2022俄文画册2.ai
        浒江2022俄文画册3.ai

Gaps vs published catalog (site edition convention)::

- DA5/10/20MQU — 24/230 × A/AS/D/DS
- SA7MU — 24/230 × DS/DST
- HVD*-40 bare (not Q/QX) — 24/230 × plain/S

Does not create DA5FU230-A/AS (album shows modulating A only on 24 V).
DA..EU is discontinued / out of RF catalog — do not seed.
"""

from __future__ import annotations

from typing import Any, Final

from catalog.etl.tech_copy import normalize_tech_copy
from catalog.models import SKU, Category, Product

CATEGORY_MQU: Final[str] = "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"
CATEGORY_SAMU: Final[str] = "elektroprivody-dlya-klapanov-dymoudaleniya"
CATEGORY_HVD: Final[str] = "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"

_MQU_NMS: Final[tuple[int, ...]] = (5, 10, 20)
_MQU_EDITIONS: Final[tuple[str, ...]] = ("A", "AS", "D", "DS")
_SAMU_EDITIONS: Final[tuple[str, ...]] = ("DS", "DST")
_VOLTS: Final[tuple[str, ...]] = ("24", "230")
_HVD_EDITIONS: Final[tuple[tuple[str, bool], ...]] = (
    ("24", False),
    ("24", True),
    ("230", False),
    ("230", True),
)

_MQU_DESC = normalize_tech_copy(
    """
Электропривод воздушной заслонки ускоренного срабатывания
без возвратной пружины. Используется в воздушных клапанах
систем ОВК (отопления, вентиляции и кондиционирования).

Назначение и особенности серии DA..MQU:
– Без возвратной пружины: положение заслонки фиксируется
  при отключении питания.
– Время поворота: ускоренное относительно серии DA..MU.
– Управление: пропорциональное (-A/-AS) или 2-/3-позиционное (-D/-DS).
– Вспомогательные переключатели 2 SPDT: суффиксы -AS / -DS.
– Степень защиты корпуса: IP54.
""".strip(),
)

_SAMU_DESC = normalize_tech_copy(
    """
Электропривод дымового клапана без возвратной пружины.
Используется в системах дымоудаления и противодымной вентиляции.

Назначение и особенности серии SA..MU:
– Управление: открыто/закрыто, 2-/3-позиционное.
– Вспомогательные переключатели: 2 SPDT (исполнения -DS / -DST).
– Исполнение -DST: термодатчик SAF72 (окружающая среда TS1 и канал TS2, 72 °C).
– Степень защиты корпуса: IP54.
""".strip(),
)

_HVD_DESC = normalize_tech_copy(
    """
Электропривод HVD — устройство для управления воздушными заслонками
в системах вентиляции и кондиционирования без возвратной пружины.

Управление: открыто/закрыто, 2-/3-позиционное.
Исполнения с вспомогательными переключателями — суффикс S в коде.
""".strip(),
)

_INSTRUCTIONS = normalize_tech_copy(
    "См. PDF инструкции серии и схемы в галерее карточки.",
)


def product_slug_damqu(nm: int) -> str:
    """Product.slug for DA{n}MQU family tile."""
    return f"privod-vozdushniy-da{nm}mqu-{nm}nm"


def product_slug_samu(nm: int) -> str:
    """Product.slug for SA{n}MU smoke tile."""
    return f"privod-dimoudaleniya-{nm}nm"


def product_slug_hvd_air(nm: int) -> str:
    """Product.slug for bare HVD-{n} air on/off tile."""
    return f"privod-vozdushniy-hvd-{nm}nm"


def _ensure_product(
    *,
    category: Category,
    slug: str,
    name: str,
    description: str,
    dry_run: bool,
) -> tuple[Product | None, bool]:
    """Return (product, created). Product is None only on dry-run create."""
    product = Product.objects.filter(slug=slug).first()
    if product is not None:
        return product, False
    if dry_run:
        return None, True
    product = Product.objects.create(
        category=category,
        name=name[:200],
        slug=slug,
        description=description,
        instructions=_INSTRUCTIONS,
    )
    return product, True


def _ensure_sku(
    *,
    product: Product | None,
    code: str,
    name: str,
    product_slug: str,
    dry_run: bool,
) -> bool:
    """Create SKU if missing. Returns True when counted as created."""
    if SKU.objects.filter(sku_code__iexact=code).exists():
        return False
    if dry_run:
        return True
    if product is None:
        return False
    SKU.objects.create(
        product=product,
        name=name[:300],
        slug=f"{product_slug}-{code.lower()}",
        sku_code=code,
        description="",
        is_published=True,
    )
    return True


def ensure_damqu_gaps(*, dry_run: bool = False) -> dict[str, Any]:
    """Create DA5/10/20MQU products and eight editions each."""
    category = Category.objects.filter(slug=CATEGORY_MQU).first()
    if category is None:
        return {
            "products_created": 0,
            "skus_created": 0,
            "error": f"missing {CATEGORY_MQU}",
        }
    products_created = 0
    skus_created = 0
    for nm in _MQU_NMS:
        p_slug = product_slug_damqu(nm)
        title = f"DA{nm}MQU | Электропривод воздушный ускоренного срабатывания без возвратной пружины, {nm} Нм"
        product, created = _ensure_product(
            category=category,
            slug=p_slug,
            name=title,
            description=_MQU_DESC,
            dry_run=dry_run,
        )
        if created:
            products_created += 1
        for volt in _VOLTS:
            for ed in _MQU_EDITIONS:
                code = f"DA{nm}MQU{volt}-{ed}"
                if _ensure_sku(
                    product=product,
                    code=code,
                    name=title,
                    product_slug=p_slug,
                    dry_run=dry_run,
                ):
                    skus_created += 1
    return {
        "products_created": products_created,
        "skus_created": skus_created,
        "dry_run": dry_run,
    }


def ensure_sa7mu(*, dry_run: bool = False) -> dict[str, Any]:
    """Create SA7MU product and four DS/DST editions."""
    category = Category.objects.filter(slug=CATEGORY_SAMU).first()
    if category is None:
        return {
            "products_created": 0,
            "skus_created": 0,
            "error": f"missing {CATEGORY_SAMU}",
        }
    nm = 7
    p_slug = product_slug_samu(nm)
    title = f"SA{nm}MU | Электропривод дымового клапана без возвратной пружины, {nm} Нм"
    product, created = _ensure_product(
        category=category,
        slug=p_slug,
        name=title,
        description=_SAMU_DESC,
        dry_run=dry_run,
    )
    products_created = 1 if created else 0
    skus_created = 0
    for volt in _VOLTS:
        for ed in _SAMU_EDITIONS:
            code = f"SA{nm}MU{volt}-{ed}"
            if _ensure_sku(
                product=product,
                code=code,
                name=title,
                product_slug=p_slug,
                dry_run=dry_run,
            ):
                skus_created += 1
    return {
        "products_created": products_created,
        "skus_created": skus_created,
        "dry_run": dry_run,
    }


def ensure_hvd_40_air(*, dry_run: bool = False) -> dict[str, Any]:
    """Create bare HVD-40 product (not Q) and four on/off editions."""
    category = Category.objects.filter(slug=CATEGORY_HVD).first()
    if category is None:
        return {
            "products_created": 0,
            "skus_created": 0,
            "error": f"missing {CATEGORY_HVD}",
        }
    nm = 40
    p_slug = product_slug_hvd_air(nm)
    title = f"HVD-{nm} | {nm} Нм Привод воздушный без возвратной пружины управление 2-/3-позиционное"
    product, created = _ensure_product(
        category=category,
        slug=p_slug,
        name=title,
        description=_HVD_DESC,
        dry_run=dry_run,
    )
    products_created = 1 if created else 0
    skus_created = 0
    for volt, aux in _HVD_EDITIONS:
        mid = f"{volt}S" if aux else volt
        code = f"HVD{mid}-{nm}"
        if _ensure_sku(
            product=product,
            code=code,
            name=title,
            product_slug=p_slug,
            dry_run=dry_run,
        ):
            skus_created += 1
    return {
        "products_created": products_created,
        "skus_created": skus_created,
        "dry_run": dry_run,
    }


def ensure_ai_catalog_gaps(*, dry_run: bool = False) -> dict[str, Any]:
    """Run all gap ensures from the 2022 AI albums."""
    parts = {
        "damqu": ensure_damqu_gaps(dry_run=dry_run),
        "sa7mu": ensure_sa7mu(dry_run=dry_run),
        "hvd40": ensure_hvd_40_air(dry_run=dry_run),
    }
    errors = [f"{key}: {row['error']}" for key, row in parts.items() if row.get("error")]
    summary: dict[str, Any] = {
        "products_created": sum(int(row.get("products_created") or 0) for row in parts.values()),
        "skus_created": sum(int(row.get("skus_created") or 0) for row in parts.values()),
        "dry_run": dry_run,
        "by_family": parts,
    }
    if errors:
        summary["error"] = "; ".join(errors)
    return summary
