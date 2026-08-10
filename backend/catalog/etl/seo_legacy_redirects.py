"""Rebuild SEO redirects so Tilda-indexed paths land on live nested SKU URLs.

Yandex/GSC still hit flat ``/privod-…``, ``/tproduct/…``, and old
``/catalog/{tilda-category}/{short-slug}`` paths. Category renames and
edition-level SKU slugs left many nginx map targets as soft-404.

This module upserts 301 rows to the current ``catalog_path_for_sku`` and
fixes static/content inventory gaps for cutover.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from django.db.models import Prefetch

from catalog.etl.normalize import PRODUCT_SLUG_REMAP
from catalog.models import SKU, Product
from catalog.series_categories import legacy_slug_aliases
from catalog.urls_paths import catalog_path_for_sku
from redirects.models import Redirect
from redirects.pathutils import normalize_path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TPRODUCT_SEED = _REPO_ROOT / "docs" / "redirects-tproduct-seed.csv"

# Inventory paths that must not 404 after DNS cutover (docs/seo-url-migration.md).
_STATIC_INVENTORY: tuple[tuple[str, str], ...] = (
    ("/sale", "/catalog"),
    ("/sitemap", "/sitemap.xml"),
    (
        "/elektroprivody-dlya-zaslonok-ventilyatsii",
        "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    ),
)

_BV_FROM_TPRODUCT = re.compile(r"(?i)\bbv(\d{3,4})\b")
_LEGACY_BRASS_PRODUCT = re.compile(r"(?i)^sharovoy-kran-(bv\d{3,4})$")


@dataclass(frozen=True, slots=True)
class SeoRedirectSummary:
    """Counts from ``ensure_seo_legacy_redirects``."""

    upserted: int
    products: int
    skus: int
    tproduct: int
    static: int
    rewritten: int


def preferred_sku_for_product(product: Product) -> SKU | None:
    """Pick a representative published edition for a family/product ЧПУ.

    Prefers 230S / 230 / 24S / 24 editions, then lexicographic ``sku_code``.
    """
    skus = list(
        product.skus.filter(is_published=True).select_related("product__category"),
    )
    if not skus:
        return None

    def score(sku: SKU) -> tuple[int, str, str]:
        code = (sku.sku_code or "").upper()
        pref = 0
        if "230S" in code:
            pref = 100
        elif re.search(r"230(?!S)", code):
            pref = 80
        elif "24S" in code:
            pref = 60
        elif re.search(r"(?:^|[^0-9])24(?:[^0-9]|$)", code):
            pref = 40
        if code.endswith("A") or code.endswith("AS"):
            pref += 5
        return (-pref, code, sku.slug)

    return sorted(skus, key=score)[0]


def resolve_legacy_slug_to_sku(slug: str) -> SKU | None:
    """Map a Tilda/flat slug to a published SKU when possible."""
    raw = (slug or "").strip().strip("/")
    if not raw:
        return None
    raw = PRODUCT_SLUG_REMAP.get(raw, raw)

    sku = (
        SKU.objects.filter(slug=raw, is_published=True)
        .select_related("product__category")
        .first()
    )
    if sku is not None:
        return sku

    product = Product.objects.filter(slug=raw).prefetch_related(
        Prefetch(
            "skus",
            queryset=SKU.objects.filter(is_published=True).select_related(
                "product__category",
            ),
        ),
    ).first()
    if product is not None:
        return preferred_sku_for_product(product)

    brass = _LEGACY_BRASS_PRODUCT.fullmatch(raw)
    if brass is not None:
        body = brass.group(1).casefold()
        product = Product.objects.filter(slug=f"8100-{body}").first()
        if product is not None:
            return preferred_sku_for_product(product)

    if "-" in raw:
        parts = raw.rsplit("-", 1)
        if len(parts) == 2:
            parent = Product.objects.filter(slug=parts[0]).first()
            if parent is not None:
                return preferred_sku_for_product(parent)
    return None


def _upsert_redirect(from_path: str, to_path: str, *, dry_run: bool) -> bool:
    """Create/update an active 301. Returns True when a write would/did happen."""
    src = normalize_path(from_path)
    dst = normalize_path(to_path)
    if src == dst:
        return False
    existing = Redirect.objects.filter(from_path=src).first()
    if (
        existing is not None
        and existing.to_path == dst
        and existing.status_code == Redirect.HTTP_MOVED_PERMANENTLY
        and existing.is_active
    ):
        return False
    if dry_run:
        return True
    Redirect.objects.update_or_create(
        from_path=src,
        defaults={
            "to_path": dst,
            "status_code": Redirect.HTTP_MOVED_PERMANENTLY,
            "is_active": True,
        },
    )
    return True


def _target_path_for_sku(sku: SKU) -> str:
    return normalize_path(catalog_path_for_sku(sku))


def _ensure_sku_paths(sku: SKU, *, dry_run: bool) -> int:
    """Flat ``/{sku.slug}`` → current nested path."""
    target = _target_path_for_sku(sku)
    if target == "/catalog":
        return 0
    return 1 if _upsert_redirect(f"/{sku.slug}", target, dry_run=dry_run) else 0


def _ensure_product_paths(product: Product, sku: SKU, *, dry_run: bool) -> int:
    """Family ЧПУ ``/{product.slug}`` (+ legacy brass + old nested category)."""
    target = _target_path_for_sku(sku)
    if target == "/catalog":
        return 0
    n = 0
    if _upsert_redirect(f"/{product.slug}", target, dry_run=dry_run):
        n += 1
    m = re.fullmatch(r"(?i)8100-(bv\d{3,4})", product.slug)
    if m is not None:
        legacy = f"sharovoy-kran-{m.group(1).casefold()}"
        if _upsert_redirect(f"/{legacy}", target, dry_run=dry_run):
            n += 1
        for alias in ("sharovye-krany", "sharoviy-kran-2-hodovoy", "sharoviy-kran-3-hodovoy"):
            if _upsert_redirect(f"/catalog/{alias}/{legacy}", target, dry_run=dry_run):
                n += 1
            if _upsert_redirect(f"/catalog/{alias}/{product.slug}", target, dry_run=dry_run):
                n += 1
    cat = ""
    if sku.product_id and sku.product.category_id:
        cat = sku.product.category.slug
    for alias in {cat, *legacy_slug_aliases().keys()}:
        if not alias:
            continue
        nested = f"/catalog/{alias}/{product.slug}"
        if normalize_path(nested) == target:
            continue
        if _upsert_redirect(nested, target, dry_run=dry_run):
            n += 1
    return n


def _rewrite_stale_redirect_targets(*, dry_run: bool) -> int:
    """Point active redirects at live nested SKU paths when possible.

    Prefer resolving the ``from_path`` leaf as a published SKU (edition URLs),
    then fall back to ``to_path`` / ``from_path`` leaf as a product/family slug.
    """
    n = 0
    for row in Redirect.objects.filter(is_active=True).iterator():
        if row.from_path.startswith(("/statyi", "/novosti", "/news")):
            continue
        from_leaf = row.from_path.rstrip("/").rsplit("/", 1)[-1]
        sku = (
            SKU.objects.filter(slug=from_leaf, is_published=True)
            .select_related("product__category")
            .first()
        )
        if sku is not None:
            target = _target_path_for_sku(sku)
            if _upsert_redirect(row.from_path, target, dry_run=dry_run):
                n += 1
            continue

        if row.to_path.startswith(("/statyi", "/novosti", "/news", "/sitemap", "/sale")):
            continue

        candidates: list[str] = []
        to_leaf = row.to_path.rstrip("/").rsplit("/", 1)[-1]
        if to_leaf and to_leaf not in {"catalog", "tproduct"}:
            candidates.append(to_leaf)
        if from_leaf and from_leaf not in candidates and from_leaf != "tproduct":
            candidates.append(from_leaf)

        target_sku: SKU | None = None
        for cand in candidates:
            target_sku = resolve_legacy_slug_to_sku(cand)
            if target_sku is not None:
                break
        if target_sku is None:
            continue
        target = _target_path_for_sku(target_sku)
        if _upsert_redirect(row.from_path, target, dry_run=dry_run):
            n += 1
    return n


def _ensure_tproduct_seed(*, dry_run: bool) -> int:
    """Upsert ``/tproduct/…`` and ``/catalog/tproduct/…`` from the seed CSV."""
    if not _TPRODUCT_SEED.is_file():
        logger.warning("tproduct_seed_missing path=%s", _TPRODUCT_SEED)
        return 0
    n = 0
    with _TPRODUCT_SEED.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            from_path = (row.get("from_path") or "").strip()
            hint = (row.get("to_path") or "").strip().strip("/")
            if not from_path:
                continue
            sku = resolve_legacy_slug_to_sku(hint) if hint else None
            if sku is None:
                match = _BV_FROM_TPRODUCT.search(from_path)
                if match is not None:
                    sku = resolve_legacy_slug_to_sku(f"sharovoy-kran-bv{match.group(1)}")
            if sku is None:
                logger.warning("tproduct_unresolved from=%s hint=%s", from_path, hint)
                continue
            target = _target_path_for_sku(sku)
            if _upsert_redirect(from_path, target, dry_run=dry_run):
                n += 1
            catalog_tproduct = from_path.replace("/tproduct/", "/catalog/tproduct/", 1)
            if catalog_tproduct != from_path:
                if _upsert_redirect(catalog_tproduct, target, dry_run=dry_run):
                    n += 1
    return n


def _ensure_static_inventory(*, dry_run: bool) -> int:
    n = 0
    for src, dst in _STATIC_INVENTORY:
        if _upsert_redirect(src, dst, dry_run=dry_run):
            n += 1
    return n


def ensure_seo_legacy_redirects(*, dry_run: bool = False) -> SeoRedirectSummary:
    """Upsert catalog + inventory redirects for SEO cutover.

    Args:
        dry_run: Count writes without mutating the DB.

    Returns:
        Summary counts.
    """
    products_n = 0
    skus_n = 0
    upserted = 0

    for product in Product.objects.prefetch_related(
        Prefetch(
            "skus",
            queryset=SKU.objects.filter(is_published=True).select_related(
                "product__category",
            ),
        ),
    ).iterator(chunk_size=200):
        sku = preferred_sku_for_product(product)
        if sku is None:
            continue
        products_n += 1
        upserted += _ensure_product_paths(product, sku, dry_run=dry_run)

    for sku in SKU.objects.filter(is_published=True).select_related("product__category").iterator():
        skus_n += 1
        upserted += _ensure_sku_paths(sku, dry_run=dry_run)

    rewritten = _rewrite_stale_redirect_targets(dry_run=dry_run)
    upserted += rewritten
    tproduct = _ensure_tproduct_seed(dry_run=dry_run)
    upserted += tproduct
    static = _ensure_static_inventory(dry_run=dry_run)
    upserted += static

    return SeoRedirectSummary(
        upserted=upserted,
        products=products_n,
        skus=skus_n,
        tproduct=tproduct,
        static=static,
        rewritten=rewritten,
    )


def ensure_article_tpost_redirects(*, dry_run: bool = False) -> int:
    """301 ``/statyi/tpost/<slug>`` → ``/statyi/<canonical>`` for articles."""
    from content.article_slug_renames import ARTICLE_SLUG_RENAMES
    from content.models import Article

    n = 0
    for old_slug, new_slug in ARTICLE_SLUG_RENAMES.items():
        target = f"/statyi/{new_slug}"
        for src in (f"/statyi/tpost/{old_slug}", f"/statyi/{old_slug}"):
            if _upsert_redirect(src, target, dry_run=dry_run):
                n += 1

    for slug in Article.objects.filter(is_published=True).values_list("slug", flat=True):
        if _upsert_redirect(f"/statyi/tpost/{slug}", f"/statyi/{slug}", dry_run=dry_run):
            n += 1
    return n
