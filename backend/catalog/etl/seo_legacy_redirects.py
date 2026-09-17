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
_TPRODUCT_SEED = _REPO_ROOT / "backend" / "redirects" / "seeds" / "redirects-tproduct-seed.csv"

# Inventory paths that must not 404 after DNS cutover (docs/seo-url-migration.md).
_STATIC_INVENTORY: tuple[tuple[str, str], ...] = (
    ("/sale", "/catalog"),
    ("/sitemap", "/sitemap.xml"),
    ("/news", "/novosti"),
    ("/collection/all", "/catalog"),
    (
        "/collection/elektroprivod-vozdushnyy-bez-vozvratnoy-pruzhiny",
        "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    ),
    ("/collection/krany-sharovye", "/catalog/sharovye-krany"),
    (
        "/collection/privod-vozdushnyy-seriya-hv",
        "/catalog/elektronnye-otkazoustoychivye-vozdushnye-privody",
    ),
    (
        "/collection/privody-protivopozharnogo-klapana",
        "/catalog/elektroprivody-protivopozharnye-i-dymovye",
    ),
    ("/obratnaya-svyaz", "/kontakty"),
    (
        "/%D0%93%D0%B4%D0%B5-%D0%BC%D0%BE%D0%B6%D0%BD%D0%BE-%D0%BA%D1%83%D0%BF%D0%B8%D1%82%D1%8C",
        "/gde-kupit",
    ),
    ("/blogs/blog", "/statyi"),
    ("/blogs/novosti", "/novosti"),
    (
        "/elektroprivody-dlya-zaslonok-ventilyatsii",
        "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    ),
    # Tilda Cyrillic menu paths (Yandex Webmaster still indexes percent-encoded URLs).
    (
        (
            "/%D0%92%D0%BE%D0%B7%D0%B4%D1%83%D1%88%D0%BD%D1%8B%D0%B5"
            "-%D0%B1%D0%B5%D0%B7-%D0%BF%D1%80%D1%83%D0%B6%D0%B8%D0%BD%D1%8B"
        ),
        "/catalog/elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    ),
    (
        (
            "/%D0%92%D0%BE%D0%B7%D0%B4%D1%83%D1%88%D0%BD%D1%8B%D0%B5"
            "-%D1%81-%D0%BF%D1%80%D1%83%D0%B6%D0%B8%D0%BD%D0%BE%D0%B9"
        ),
        "/catalog/elektroprivody-s-pruzhinnym-vozvratom",
    ),
    (
        "/%D0%94%D0%BB%D1%8F-%D0%B4%D1%8B%D0%BC%D0%BE%D1%83%D0%B4%D0%B0%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F",
        "/catalog/elektroprivody-dlya-klapanov-dymoudaleniya",
    ),
    (
        "/%D0%9A%D1%80%D0%B0%D0%BD%D1%8B-%D0%A8%D0%B0%D1%80%D0%BE%D0%B2%D1%8B%D0%B5",
        "/catalog/sharovye-krany",
    ),
    (
        "/%D0%9F%D1%80%D0%B8%D0%B2%D0%BE%D0%B4%D1%8B-%D1%83%D1%81%D0%BA%D0%BE%D1%80%D0%B5%D0%BD%D0%BD%D1%8B%D0%B5",
        "/catalog/elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    ),
    (
        (
            "/%D0%A1%D1%82%D0%B0%D1%82%D1%8C%D0%B8/"
            "%D1%81%D0%BF%D0%B5%D1%86%D0%B8%D1%84%D0%B8%D0%BA%D0%B0%D1%86%D0%B8%D1%8F-"
            "%D0%BF%D1%80%D0%B8%D0%B2%D0%BE%D0%B4%D0%BE%D0%B2"
        ),
        "/statyi/spetsifikatsiya-modelnogo-ryada-privodov",
    ),
    (
        "/%D0%A1%D1%82%D0%B0%D1%82%D1%8C%D0%B8/markirovka-privodov-hoocon",
        "/statyi",
    ),
    (
        "/%D0%BF%D1%80%D0%B8%D0%B2%D0%BE%D0%B4-%D1%83%D1%81%D0%BA%D0%BE%D1%80%D0%B5%D0%BD%D0%BD%D1%8B%D0%B9",
        "/catalog/elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    ),
)

# Old Tilda ``/blogs/blog/…`` paths → nearest live article.
_BLOG_ARTICLE_INVENTORY: tuple[tuple[str, str], ...] = (
    (
        "/blogs/blog/obschaya-tablitsa-podbora-elektroprivodov-bez-pruzhinnogo-vozvrata",
        "/statyi/podbor-privoda-po-momentu-i-ploshchadi",
    ),
    (
        "/blogs/blog/po-kakomu-printsipu-postroena-rabota-sistemy-udaleniya-dyma",
        "/statyi/protivopozharnye-vs-dymoudaleniya-privody",
    ),
    (
        "/blogs/blog/sharovie-krany-konstrukcia",
        "/statyi/sharovye-krany-vidy-konstruktsiya",
    ),
    ("/blogs/blog/ip54", "/statyi/sertifikaty-ce-ul-eac-elektroprivody-ovk"),
    ("/blogs/skachat-tehnicheskuyu-dokumentatsiyu", "/statyi"),
    ("/blogs/skachat-tehnicheskuyu-dokumentatsiyu/dafu", "/statyi"),
    (
        "/blogs/skachat-tehnicheskuyu-dokumentatsiyu/hvd-privod-vozdushnyy",
        "/statyi",
    ),
    ("/blogs/novosti/nerabochie-dni", "/novosti"),
    ("/blogs/novosti/poluchen-sertifikat-eac", "/novosti"),
)

_BV_FROM_TPRODUCT = re.compile(r"(?i)\bbv(\d{3,4})\b")
_LEGACY_BRASS_PRODUCT = re.compile(r"(?i)^sharovoy-kran-(bv\d{3,4})$")
_LEGACY_BRASS_DVUH = re.compile(r"(?i)^sharovoy-dvuhhodoviy-kran-(bv\d{3,4})$")
_EDITION_SUFFIX = re.compile(r"^(?P<voltage>24|230)v-(?P<control>ds|dst|d)$", re.I)
_SALE_SUFFIX = re.compile(r"(?i)-sale$")


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


def _sku_matches_edition_tokens(sku: SKU, *, voltage: str, control: str) -> bool:
    """True when a SKU slug/code matches a Tilda edition suffix like ``24v-dst``."""
    slug = sku.slug.casefold()
    code = (sku.sku_code or "").casefold()
    blob = f"{slug} {code}"
    if voltage == "230":
        if "230" not in blob:
            return False
    elif not re.search(r"(?:^|[^0-9])24(?:[^0-9]|$)", blob):
        return False
    if control == "dst":
        return slug.endswith("-dst") or code.endswith("-dst")
    if control == "ds":
        return slug.endswith("-ds") or code.endswith("-ds")
    return (slug.endswith("-d") or code.endswith("-d")) and not (slug.endswith("-ds") or code.endswith("-ds"))


def _match_edition_sku(product: Product, edition_suffix: str) -> SKU | None:
    """Pick a published SKU edition from a Tilda human-readable suffix."""
    suffix = edition_suffix.strip().strip("-")
    if not suffix:
        return None
    match = _EDITION_SUFFIX.match(suffix)
    if match is not None:
        skus = list(product.skus.filter(is_published=True).select_related("product__category"))
        hits = [
            sku
            for sku in skus
            if _sku_matches_edition_tokens(
                sku,
                voltage=match.group("voltage"),
                control=match.group("control").casefold(),
            )
        ]
        if len(hits) == 1:
            return hits[0]
        if hits:
            return sorted(hits, key=lambda sku: (sku.sku_code or "", sku.slug))[0]
    needle = suffix.casefold()
    for sku in product.skus.filter(is_published=True).select_related("product__category"):
        code = (sku.sku_code or "").casefold()
        if code and (code == needle or needle.endswith(code) or code in needle):
            return sku
    return None


def _resolve_by_embedded_sku_code(raw: str) -> SKU | None:
    """Match Tilda flat paths that embed a ``sku_code`` (e.g. ``…-sa15fu24-dst``)."""
    lowered = raw.casefold()
    best: tuple[int, SKU] | None = None
    for sku in SKU.objects.filter(is_published=True).select_related("product__category").iterator():
        code = (sku.sku_code or "").casefold()
        if not code or code not in lowered:
            continue
        if best is None or len(code) > best[0]:
            best = (len(code), sku)
    return best[1] if best is not None else None


def _resolve_product_with_suffix(raw: str) -> SKU | None:
    """Walk slug prefixes to a Product, then match an edition suffix when present."""
    parts = raw.split("-")
    for end in range(len(parts), 1, -1):
        candidate = "-".join(parts[:end])
        product = (
            Product.objects.filter(slug=candidate)
            .prefetch_related(
                Prefetch(
                    "skus",
                    queryset=SKU.objects.filter(is_published=True).select_related(
                        "product__category",
                    ),
                ),
            )
            .first()
        )
        if product is None:
            continue
        suffix = "-".join(parts[end:])
        if suffix:
            edition = _match_edition_sku(product, suffix)
            if edition is not None:
                return edition
        return preferred_sku_for_product(product)
    return None


def resolve_legacy_slug_to_sku(slug: str) -> SKU | None:
    """Map a Tilda/flat slug to a published SKU when possible."""
    raw = (slug or "").strip().strip("/")
    if not raw:
        return None
    raw = _SALE_SUFFIX.sub("", raw)
    raw = PRODUCT_SLUG_REMAP.get(raw, raw)

    sku = SKU.objects.filter(slug=raw, is_published=True).select_related("product__category").first()
    if sku is not None:
        return sku

    sku = (
        SKU.objects.filter(sku_code__iexact=raw.replace("-", ""), is_published=True)
        .select_related("product__category")
        .first()
    )
    if sku is not None:
        return sku
    sku = SKU.objects.filter(sku_code__iexact=raw, is_published=True).select_related("product__category").first()
    if sku is not None:
        return sku

    product = (
        Product.objects.filter(slug=raw)
        .prefetch_related(
            Prefetch(
                "skus",
                queryset=SKU.objects.filter(is_published=True).select_related(
                    "product__category",
                ),
            ),
        )
        .first()
    )
    if product is not None:
        return preferred_sku_for_product(product)

    brass = _LEGACY_BRASS_PRODUCT.fullmatch(raw)
    if brass is not None:
        body = brass.group(1).casefold()
        product = Product.objects.filter(slug=f"8100-{body}").first()
        if product is not None:
            return preferred_sku_for_product(product)

    brass_dvuh = _LEGACY_BRASS_DVUH.fullmatch(raw)
    if brass_dvuh is not None:
        return resolve_legacy_slug_to_sku(f"sharovoy-kran-{brass_dvuh.group(1).casefold()}")

    embedded = _resolve_by_embedded_sku_code(raw)
    if embedded is not None:
        return embedded

    return _resolve_product_with_suffix(raw)


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
        body = m.group(1).casefold()
        for legacy in (
            f"sharovoy-kran-{body}",
            f"sharovoy-dvuhhodoviy-kran-{body}",
        ):
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
        sku = SKU.objects.filter(slug=from_leaf, is_published=True).select_related("product__category").first()
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
    for src, dst in _BLOG_ARTICLE_INVENTORY:
        if _upsert_redirect(src, dst, dry_run=dry_run):
            n += 1
    return n


def _ensure_store_paths(*, dry_run: bool) -> int:
    """301 ``/store/{sku_code}`` → live nested SKU path when code resolves."""
    n = 0
    seen: set[str] = set()
    for sku in SKU.objects.filter(is_published=True).select_related("product__category").iterator():
        code = (sku.sku_code or "").strip()
        if not code:
            continue
        for segment in {code.casefold(), code.lower()}:
            if segment in seen:
                continue
            seen.add(segment)
            target = _target_path_for_sku(sku)
            if _upsert_redirect(f"/store/{segment}", target, dry_run=dry_run):
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
    store = _ensure_store_paths(dry_run=dry_run)
    upserted += store

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
        for src in (
            f"/statyi/tpost/{old_slug}",
            f"/statyi/{old_slug}",
            f"/tpost/{old_slug}",
        ):
            if _upsert_redirect(src, target, dry_run=dry_run):
                n += 1

    for slug in Article.objects.filter(is_published=True).values_list("slug", flat=True):
        for src in (f"/statyi/tpost/{slug}", f"/tpost/{slug}"):
            if _upsert_redirect(src, f"/statyi/{slug}", dry_run=dry_run):
                n += 1
    return n
