"""Ensure BR-M / BR-ML adapter cards for ball-valve RFQ kits.

Copy from partner dealer pages; **photos** are local processed assets under
``catalog/etl/data/adapters-br/`` (downloaded once, enhanced, committed) —
never hotlinked from hoocon.spb.ru.

Canon for spring vs non-spring matches ``ball_valve_kit.resolve_bracket_for_drive``
and page titles on the partner site. Partner «Подходит для электроприводов»
values are swapped relative to those titles — we do **not** copy that field
verbatim.

Usage::

    poetry run python manage.py ensure_br_adapters
    poetry run python manage.py ensure_br_adapters --dry-run
    poetry run python manage.py ensure_br_adapters --force-images
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from django.core.files.base import ContentFile
from django.utils.text import slugify

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.tech_copy import normalize_tech_copy
from catalog.etl.webp import enhance_transparent_catalog_photo_bytes
from catalog.models import SKU, Category, Product, ProductImage
from catalog.series_categories import adapters_category_slug

logger = logging.getLogger(__name__)

CATEGORY_SLUG: Final[str] = adapters_category_slug()
CATEGORY_NAME: Final[str] = "Адаптеры"
_LEGACY_CATEGORY_SLUG: Final[str] = "adaptery-bv-br"
_DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data" / "adapters-br"
_LOCAL_SOURCE_PREFIX: Final[str] = "https://hoocon.ru/.local-assets/adapters-br/"

_SERIES: Final[str] = "BV BR (8100 / 8100Q-BV…)"
_APPLICATION: Final[str] = "для шарового крана, регулирующего клапана"

# Partner-site «заводские» поля — не на карточке (один бренд / изготовитель).
# ``control`` — slug совпадает с фасетом «Управление» и путает фильтры адаптеров.
_OMIT_ATTR_SLUGS: Final[frozenset[str]] = frozenset(
    {
        "country-of-origin",
        "brand-origin",
        "trademark",
        "warranty",
        "manufacturer",
        "control",
    },
)


@dataclass(frozen=True, slots=True)
class BrAdapterSpec:
    """One adapter SKU seeded from the partner catalog."""

    sku_code: str
    product_slug: str
    sku_slug: str
    name: str
    drive_kind: str
    compatible_actuators: str
    partner_indexes: str
    asset_stem: str
    partner_url: str
    description: str


# Short attr for catalog card / facet; detail stays in description.
# Families for linking: catalog.compatible_positions.
_BR_M_ACTUATORS: Final[str] = "DA4MU…DA16MU, DA8MQU…DA16MQU (24/230 В)"
_BR_ML_ACTUATORS: Final[str] = "DA3FU, DA5FU (24/230 В)"

_ADAPTERS: Final[tuple[BrAdapterSpec, ...]] = (
    BrAdapterSpec(
        sku_code="BR-M",
        product_slug="adapter-br-m",
        sku_slug="adapter-br-m",
        name="BR-M | Адаптер под привод без возвратной пружины",
        drive_kind="без возвратной пружины (MU / MQU)",
        compatible_actuators=_BR_M_ACTUATORS,
        partner_indexes="DA4MU, DA6MU, DA8MU, DA8MQU, DA16MU, DA16MQU (24/230 В)",
        asset_stem="br-m",
        partner_url=(
            "https://hoocon.spb.ru/production/catalog/adaptery-bv-br/"
            "adapter_hoocon_br_m_pod_privod_bez_vozvratnoy_pruzhiny/"
        ),
        description=normalize_tech_copy(
            """
Адаптер (кронштейн) Hoocon BR-M для установки электропривода
без возвратной пружины на шаровой регулирующий кран серии BV BR
(8100 / 8100Q-BV…).

Назначение:
– Соединяет привод DA…MU / DA…MQU с корпусом латунного крана 8100.
– В RFQ выбирается для приводов без пружинного возврата
  (см. комплектацию шаровых кранов).

Совместимость по каталогу шаровых 8100 (не вся серия DA):
– DA4MU, DA6MU, DA8MU, DA8MQU, DA16MU, DA16MQU — 24 В и 230 В;
– исполнения −D / −DS / −A / −AS.
Не подходит для DA…FU (нужен BR-ML). Конкретный момент и напряжение
на DN — в карточке крана («совместимый привод»).
""".strip(),
        ),
    ),
    BrAdapterSpec(
        sku_code="BR-ML",
        product_slug="adapter-br-ml",
        sku_slug="adapter-br-ml",
        name="BR-ML | Адаптер под привод с возвратной пружиной",
        drive_kind="с возвратной пружиной (FU)",
        compatible_actuators=_BR_ML_ACTUATORS,
        partner_indexes="DA3FU24, DA3FU230, DA5FU24, DA5FU230",
        asset_stem="br-ml",
        partner_url=(
            "https://hoocon.spb.ru/production/catalog/adaptery-bv-br/"
            "adapter_hoocon_br_ml_pod_privod_s_vozvratnoy_pruzhinoy/"
        ),
        description=normalize_tech_copy(
            """
Адаптер (кронштейн) Hoocon BR-ML для установки электропривода
с возвратной пружиной на шаровой регулирующий кран серии BV BR
(8100 / 8100Q-BV…).

Назначение:
– Соединяет привод DA…FU с корпусом латунного крана 8100.
– В RFQ выбирается автоматически для серий DA…FU
  (см. комплектацию шаровых кранов).

Совместимость по каталогу шаровых 8100 (не вся серия DA):
– DA3FU24 и DA3FU230 (−D / −DS);
– DA5FU24 и DA5FU230 (−D / −DS / −A / −AS).
Не подходит для DA…MU / DA…MQU (нужен BR-M). На части DN в 8100
перечислены только MU/MQU — там BR-ML в комплекте не используется.
""".strip(),
        ),
    ),
)


def adapters_data_dir() -> Path:
    """Directory with committed adapter source JPG / enhanced WebP."""
    return _DATA_DIR


def local_asset_source_url(stem: str) -> str:
    """Stable ``source_url`` marker for local pack files (not a hotlink)."""
    return f"{_LOCAL_SOURCE_PREFIX}{stem}.webp"


def resolve_adapter_photo_bytes(stem: str) -> bytes:
    """Load local adapter photo and return enhanced WebP bytes.

    Preference order::

        1. ``{stem}-nobg-source.png`` — cut-out, upscale to 1600, WebP q55
        2. ``{stem}-source.jpg`` — studio JPEG enhance
        3. ``{stem}.webp`` — re-encode prebuilt

    Args:
        stem: ``br-m`` or ``br-ml``.

    Returns:
        Enhanced WebP payload.

    Raises:
        FileNotFoundError: when no local asset exists.
    """
    nobg = _DATA_DIR / f"{stem}-nobg-source.png"
    source = _DATA_DIR / f"{stem}-source.jpg"
    prebuilt = _DATA_DIR / f"{stem}.webp"
    if nobg.is_file():
        return enhance_transparent_catalog_photo_bytes(nobg.read_bytes())
    if source.is_file():
        from catalog.etl.webp import enhance_catalog_photo_bytes

        return enhance_catalog_photo_bytes(source.read_bytes())
    if prebuilt.is_file():
        return enhance_transparent_catalog_photo_bytes(prebuilt.read_bytes())
    raise FileNotFoundError(f"Missing adapter photo for {stem} under {_DATA_DIR}")


def ensure_adapters_category(*, dry_run: bool = False) -> Category | None:
    """Get or create the adapters category (migrate legacy ``adaptery-bv-br``)."""
    category = Category.objects.filter(slug=CATEGORY_SLUG).first()
    if category is None:
        legacy = Category.objects.filter(slug=_LEGACY_CATEGORY_SLUG).first()
        if legacy is not None:
            if dry_run:
                return legacy
            legacy.slug = CATEGORY_SLUG
            legacy.name = CATEGORY_NAME
            legacy.save(update_fields=["slug", "name", "updated_at"])
            _ensure_category_redirect(
                from_slug=_LEGACY_CATEGORY_SLUG,
                to_slug=CATEGORY_SLUG,
            )
            return legacy
        if dry_run:
            return None
        return Category.objects.create(slug=CATEGORY_SLUG, name=CATEGORY_NAME)

    dirty = False
    if category.name != CATEGORY_NAME:
        category.name = CATEGORY_NAME
        dirty = True
    if dirty and not dry_run:
        category.save(update_fields=["name", "updated_at"])
    # Drop empty legacy row if both somehow exist.
    if not dry_run:
        legacy = Category.objects.filter(slug=_LEGACY_CATEGORY_SLUG).first()
        if legacy is not None and legacy.pk != category.pk:
            if legacy.products.exists():
                for product in legacy.products.all():
                    product.category = category
                    product.save(update_fields=["category", "updated_at"])
            legacy.delete()
            _ensure_category_redirect(
                from_slug=_LEGACY_CATEGORY_SLUG,
                to_slug=CATEGORY_SLUG,
            )
    return category


def _ensure_category_redirect(*, from_slug: str, to_slug: str) -> None:
    """301 ``/catalog/{from}`` → ``/catalog/{to}`` when missing."""
    from redirects.models import Redirect
    from redirects.pathutils import normalize_path

    from_path = normalize_path(f"/catalog/{from_slug}")
    to_path = normalize_path(f"/catalog/{to_slug}")
    if from_path == to_path:
        return
    if Redirect.objects.filter(from_path=from_path).exists():
        return
    Redirect.objects.create(
        from_path=from_path,
        to_path=to_path,
        status_code=Redirect.HTTP_MOVED_PERMANENTLY,
        is_active=True,
    )


def _ensure_product(
    *,
    category: Category,
    spec: BrAdapterSpec,
    dry_run: bool,
) -> tuple[Product | None, bool]:
    product = Product.objects.filter(slug=spec.product_slug).first()
    if product is not None:
        dirty = False
        if product.category_id != category.id:
            product.category = category
            dirty = True
        if product.name != spec.name[:200]:
            product.name = spec.name[:200]
            dirty = True
        if (product.description or "").strip() != spec.description.strip():
            product.description = spec.description
            dirty = True
        if dirty and not dry_run:
            product.save()
        return product, False
    if dry_run:
        return None, True
    product = Product.objects.create(
        category=category,
        name=spec.name[:200],
        slug=spec.product_slug,
        description=spec.description,
    )
    return product, True


def _ensure_sku(
    *,
    product: Product | None,
    spec: BrAdapterSpec,
    dry_run: bool,
) -> tuple[SKU | None, bool]:
    sku = SKU.objects.filter(sku_code__iexact=spec.sku_code).first()
    if sku is not None:
        dirty = False
        if product is not None and sku.product_id != product.id:
            sku.product = product
            dirty = True
        if sku.slug != spec.sku_slug:
            sku.slug = spec.sku_slug
            dirty = True
        if sku.name != spec.name[:300]:
            sku.name = spec.name[:300]
            dirty = True
        if (sku.description or "").strip() != spec.description.strip():
            sku.description = spec.description
            dirty = True
        if not sku.is_published:
            sku.is_published = True
            dirty = True
        if dirty and not dry_run:
            sku.save()
        return sku, False
    if dry_run or product is None:
        return None, True
    sku = SKU.objects.create(
        product=product,
        name=spec.name[:300],
        slug=spec.sku_slug,
        sku_code=spec.sku_code,
        description=spec.description,
        is_published=True,
        stock_qty=0,
    )
    return sku, True


def _write_attrs(sku: SKU, spec: BrAdapterSpec) -> None:
    from catalog.models import AttributeValue

    rows: tuple[tuple[str, str, str], ...] = (
        ("equipment-type", "Тип оборудования", "Адаптеры под электропривод для шаровых кранов"),
        ("series", "Серия", _SERIES),
        ("application", "Применение", _APPLICATION),
        ("valve-type", "Тип клапана/крана", "Адаптер"),
        ("drive-kind", "Подходит для электроприводов", spec.drive_kind),
        ("compatible-actuators", "Совместимый привод", spec.compatible_actuators),
        ("partner-indexes", "Индексы совместимых моделей", spec.partner_indexes),
        ("bracket", "Кронштейн", spec.sku_code),
    )
    for slug, name, value in rows:
        set_sku_attribute(sku, slug=slug, name=name, value=value)
    # Drop one-brand boilerplate and misleading «Управление» (slug=control).
    AttributeValue.objects.filter(
        sku=sku,
        attribute__slug__in=_OMIT_ATTR_SLUGS,
    ).delete()


def _attach_image(
    sku: SKU,
    *,
    stem: str,
    alt: str,
    force: bool,
    dry_run: bool,
) -> str:
    """Attach enhanced local photo as WebP ProductImage.

    Returns:
        ``skipped`` | ``exists`` | ``written`` | ``error``.
    """
    source_url = local_asset_source_url(stem)
    same_source = ProductImage.objects.filter(sku=sku, source_url=source_url).first()
    if same_source is not None and same_source.image and same_source.is_published and not force:
        return "exists"

    partner_heroes = (
        ProductImage.objects.filter(
            sku=sku,
            is_published=True,
        )
        .exclude(image="")
        .filter(source_url__startswith="https://hoocon.spb.ru/")
    )
    other_local = ProductImage.objects.filter(sku=sku, is_published=True).exclude(image="")
    if same_source is not None:
        other_local = other_local.exclude(pk=same_source.pk)
    other_local = other_local.exclude(source_url__startswith="https://hoocon.spb.ru/")
    if other_local.exists() and not force and same_source is None:
        return "exists"
    # Partner hotlinks are replaced by the local pack even without --force.
    upgrade_from_partner = partner_heroes.exists() and same_source is None
    if dry_run:
        return "skipped"
    try:
        webp = resolve_adapter_photo_bytes(stem)
    except (OSError, FileNotFoundError, ValueError) as exc:
        logger.warning("BR adapter image skip %s: %s", stem, exc)
        return "error"

    stale = ProductImage.objects.filter(sku=sku)
    if same_source is not None:
        stale = stale.exclude(pk=same_source.pk)
    for row in stale:
        is_partner = (row.source_url or "").startswith("https://hoocon.spb.ru/")
        if force or is_partner or upgrade_from_partner:
            if row.is_published:
                row.is_published = False
                row.save(update_fields=["is_published", "updated_at"])

    safe = slugify(sku.sku_code) or f"sku-{sku.pk}"
    filename = f"{safe}-local.webp"
    if same_source is not None:
        same_source.alt = alt[:300]
        same_source.sort_order = 0
        same_source.is_published = True
        same_source.source_url = source_url
        same_source.image.save(filename, ContentFile(webp), save=False)
        same_source.save()
        return "written"

    img = ProductImage(
        sku=sku,
        alt=alt[:300],
        source_url=source_url,
        sort_order=0,
        is_published=True,
    )
    img.image.save(filename, ContentFile(webp), save=False)
    img.save()
    return "written"


def ensure_br_adapters(
    *,
    dry_run: bool = False,
    force_images: bool = False,
) -> dict[str, Any]:
    """Create/update BR-M and BR-ML Product/SKU cards with local enhanced photos."""
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "force_images": force_images,
        "category": CATEGORY_SLUG,
        "data_dir": str(_DATA_DIR),
        "products_created": 0,
        "skus_created": 0,
        "attrs_written": 0,
        "images": {},
        "by_code": {},
    }
    category = ensure_adapters_category(dry_run=dry_run)
    if category is None:
        if dry_run:
            summary["note"] = "category would be created"
            for spec in _ADAPTERS:
                product_exists = Product.objects.filter(slug=spec.product_slug).exists()
                sku_exists = SKU.objects.filter(sku_code__iexact=spec.sku_code).exists()
                summary["products_created"] += 0 if product_exists else 1
                summary["skus_created"] += 0 if sku_exists else 1
                summary["images"][spec.sku_code] = "skipped"
                summary["by_code"][spec.sku_code] = {
                    "product_slug": spec.product_slug,
                    "sku_slug": spec.sku_slug,
                    "product_created": not product_exists,
                    "sku_created": not sku_exists,
                    "partner_url": spec.partner_url,
                    "image": "skipped",
                }
            return summary
        summary["error"] = f"missing {CATEGORY_SLUG}"
        return summary

    for spec in _ADAPTERS:
        product, p_created = _ensure_product(category=category, spec=spec, dry_run=dry_run)
        if p_created:
            summary["products_created"] += 1
        sku, s_created = _ensure_sku(product=product, spec=spec, dry_run=dry_run)
        if s_created:
            summary["skus_created"] += 1
        image_status = "skipped"
        if sku is not None and not dry_run:
            _write_attrs(sku, spec)
            summary["attrs_written"] += 1
            image_status = _attach_image(
                sku,
                stem=spec.asset_stem,
                alt=spec.name,
                force=force_images,
                dry_run=False,
            )
        summary["images"][spec.sku_code] = image_status
        summary["by_code"][spec.sku_code] = {
            "product_slug": spec.product_slug,
            "sku_slug": spec.sku_slug,
            "product_created": p_created,
            "sku_created": s_created,
            "partner_url": spec.partner_url,
            "image": image_status,
            "source_url": local_asset_source_url(spec.asset_stem),
        }
    return summary
