"""Scrape product pages listed on https://hoocon.ru/sitemap (HTML map).

Tilda products are regular pages (/privod-…, /tproduct/…), not a DRF catalog.
This command:
1. Parses /sitemap for product links
2. Fetches each page (title, meta, body bullets, CDN images)
3. Updates matching Product + SKU cards
4. Creates missing ball-valve lines (BV332+) from store CSV when linked

Usage:
  poetry run python manage.py scrape_hoocon_sitemap \\
    --store-csv ~/Downloads/store-….csv \\
    --import-images
"""

from __future__ import annotations

import csv
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from catalog.etl.html_text import (
    compose_product_description,
    extract_product_text_blocks,
    html_to_text,
)
from catalog.etl.sku_variant import filter_description_for_variant, parse_sku_variant
from catalog.etl.slug_map import build_uid_slug_map, load_tproduct_slug_map
from catalog.etl.webp import convert_bytes_to_webp
from catalog.models import SKU, Category, Product, ProductImage

logger = logging.getLogger(__name__)

USER_AGENT = "HooconCMS-SitemapScrape/1.0 (+https://hoocon.ru)"
SITE = "https://hoocon.ru"
SITEMAP_PATH = "/sitemap"
DOWNLOAD_TIMEOUT_S = 35
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_PAGE = 3

_HREF = re.compile(r"""href=["']([^"']+)["']""", re.I)
_TITLE = re.compile(r"<title>([^<]+)</title>", re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_META_DESC = re.compile(
    r"""<meta[^>]+(?:name=["']description["'][^>]+content=["']([^"']+)|"""
    r"""content=["']([^"']+)["'][^>]+name=["']description["'])""",
    re.I,
)
_OG_IMAGE = re.compile(
    r"""property=["']og:image["'][^>]+content=["']([^"']+)["']""",
    re.I,
)
_CDN_IMG = re.compile(
    r"https://static\.tildacdn\.com/[^\s\"'<>]+\.(?:jpg|jpeg|png|webp)",
    re.I,
)
_TPRODUCT_UID = re.compile(r"(?:^|/)tproduct/(\d+)", re.I)


@dataclass
class ScrapedPage:
    """Parsed fields from one hoocon.ru product page."""

    url: str
    slug: str
    title: str = ""
    meta_description: str = ""
    text_blocks: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)


def _fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def _download_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:  # noqa: S310
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError(f"too large: {url}")
            chunks.append(chunk)
    return b"".join(chunks)


def parse_sitemap_product_urls(html: str, tproduct_map: dict[str, str]) -> list[tuple[str, str]]:
    """Return list of (absolute_url, canonical_slug) from /sitemap HTML.

    Args:
        html: Raw HTML of https://hoocon.ru/sitemap
        tproduct_map: uid → canonical slug from redirects seed

    Returns:
        Deduplicated product page targets.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for href in _HREF.findall(html):
        full = urljoin(SITE, href)
        parsed = urlparse(full)
        if not parsed.netloc.endswith("hoocon.ru"):
            continue
        path = parsed.path.strip("/")
        if not path:
            continue
        low = path.lower()
        # Skip non-product sections
        if low in {
            "sitemap",
            "catalog",
            "company",
            "gde-kupit",
            "oferta",
            "privacy-policy",
            "terms",
            "footer",
            "rss.xml",
            "members/login",
            "elektroprivody-dlya-zaslonok-ventilyatsii",
        }:
            continue
        if low.startswith(("news/", "statyi", "novosti", "page")):
            continue

        slug: str | None = None
        uid_match = _TPRODUCT_UID.search(path)
        if uid_match:
            slug = tproduct_map.get(uid_match.group(1))
            if not slug:
                # Fallback: keep tproduct path tail as temporary slug
                slug = path.split("/")[-1]
        elif low.startswith("privod-") or low.startswith("sharovoy-kran-"):
            slug = path
        elif "privod" in low or "sharov" in low:
            slug = path.split("/")[-1] if "/tproduct/" not in low else None

        if not slug:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        out.append((full, slug))
    return out


def scrape_product_page(url: str, slug: str) -> ScrapedPage:
    """Fetch and parse one product page."""
    html = _fetch(url)
    page = ScrapedPage(url=url, slug=slug)

    h1 = _H1.search(html)
    if h1:
        page.title = html_to_text(h1.group(1))[:300]
    if not page.title:
        t = _TITLE.search(html)
        if t:
            page.title = html_to_text(t.group(1))[:300]

    md = _META_DESC.search(html)
    if md:
        page.meta_description = html_to_text(md.group(1) or md.group(2) or "")

    # Prefer Tilda product copy blocks over regex-on-raw-HTML (avoids chrome noise).
    page.text_blocks = extract_product_text_blocks(html)[:2]

    images: list[str] = []
    for match in _OG_IMAGE.finditer(html):
        u = match.group(1).strip()
        if "og-image.jpg" in u:
            continue
        if u not in images:
            images.append(u)
    for u in _CDN_IMG.findall(html):
        if "/-/resizeb/" in u or "web-app-manifest" in u:
            continue
        if u not in images:
            images.append(u)
    page.image_urls = images[:MAX_IMAGES_PER_PAGE]
    return page


def _compose_description(page: ScrapedPage) -> str:
    return compose_product_description(
        meta_description=page.meta_description,
        html_blocks=page.text_blocks,
    )


def _ensure_category_for_slug(slug: str) -> Category:
    """Assign a specification category for a newly created product line."""
    from catalog.series_categories import classify_series_category, spec_categories

    target_slug = classify_series_category(slug)
    for spec in spec_categories():
        if spec.slug == target_slug:
            cat, _ = Category.objects.get_or_create(
                slug=spec.slug,
                defaults={"name": spec.name},
            )
            return cat
    # Fallback: first actuator family from the series table.
    first = spec_categories(include_ball_valves=False)[0]
    cat, _ = Category.objects.get_or_create(
        slug=first.slug,
        defaults={"name": first.name},
    )
    return cat


class Command(BaseCommand):
    """Import product card content from hoocon.ru/sitemap HTML pages."""

    help = "Scrape https://hoocon.ru/sitemap product pages into catalog cards"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--store-csv",
            default=str(Path.home() / "Downloads" / "store-12190035-202607191843.csv"),
            help="Tilda store CSV for missing editions (BV332+)",
        )
        parser.add_argument(
            "--seed-csv",
            default="",
            help="redirects-tproduct-seed.csv (default: docs/…)",
        )
        parser.add_argument(
            "--import-images",
            action="store_true",
            help="Download page images as WebP ProductImage",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max pages to scrape (0 = all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse only, no DB writes",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from django.conf import settings

        seed = options["seed_csv"].strip()
        if not seed:
            seed = str(
                Path(settings.BASE_DIR).resolve().parent
                / "backend"
                / "redirects"
                / "seeds"
                / "redirects-tproduct-seed.csv"
            )
        seed_csv = Path(seed).expanduser().resolve()
        store_csv = Path(options["store_csv"]).expanduser().resolve()
        dry_run = bool(options["dry_run"])
        limit = int(options["limit"] or 0)
        do_images = bool(options["import_images"])

        tproduct_map = load_tproduct_slug_map(seed_csv)
        uid_slug = build_uid_slug_map(
            seed_csv=seed_csv,
            store_csv=store_csv if store_csv.is_file() else None,
        )
        tproduct_map = {**tproduct_map, **uid_slug}

        self.stdout.write(f"Fetching {SITE}{SITEMAP_PATH} …")
        try:
            sitemap_html = _fetch(f"{SITE}{SITEMAP_PATH}")
        except (HTTPError, URLError, OSError) as exc:
            raise CommandError(f"Cannot fetch sitemap: {exc}") from exc

        targets = parse_sitemap_product_urls(sitemap_html, tproduct_map)
        self.stdout.write(f"Product pages on sitemap: {len(targets)}")

        csv_editions = self._load_csv_editions(store_csv) if store_csv.is_file() else {}
        if not hasattr(self, "_csv_parents"):
            self._csv_parents = {}

        updated_products = 0
        updated_skus = 0
        created_products = 0
        created_skus = 0
        images_added = 0
        failed = 0

        for i, (url, slug) in enumerate(targets, start=1):
            if limit and i > limit:
                break
            try:
                page = scrape_product_page(url, slug)
            except (HTTPError, URLError, OSError, TimeoutError) as exc:
                failed += 1
                self.stderr.write(f"  FAIL {url}: {exc}")
                continue

            self.stdout.write(f"  [{i}/{len(targets)}] {slug} — {page.title[:50]}")

            if dry_run:
                time.sleep(0.15)
                continue

            product = Product.objects.filter(slug=slug).first()
            if product is None:
                # Create from page + CSV editions if available
                product, n_skus = self._create_product_from_page(page, csv_editions)
                if product is None:
                    self.stderr.write(f"  skip no product match: {slug}")
                    time.sleep(0.15)
                    continue
                created_products += 1
                created_skus += n_skus

            desc = _compose_description(page)
            changed = False
            if page.title and product.name != page.title:
                product.name = page.title[:200]
                changed = True
            if desc and desc != product.description:
                product.description = desc
                changed = True
            if changed:
                product.save()
                updated_products += 1

            skus = list(SKU.objects.filter(product=product))
            for sku in skus:
                sku_desc = filter_description_for_variant(
                    desc,
                    parse_sku_variant(sku.sku_code),
                )
                if sku_desc and sku_desc != sku.description:
                    sku.description = sku_desc
                    sku.save(update_fields=["description", "updated_at"])
                    updated_skus += 1

            if do_images and page.image_urls and skus:
                images_added += self._attach_images(skus, page)

            time.sleep(0.25)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. products_updated={updated_products} skus_updated={updated_skus} "
                f"products_created={created_products} skus_created={created_skus} "
                f"images_added={images_added} failed={failed} dry_run={dry_run}",
            ),
        )

    def _load_csv_editions(self, store_csv: Path) -> dict[str, list[dict[str, str]]]:
        """parent_uid → list of edition rows from store CSV."""
        by_parent: dict[str, list[dict[str, str]]] = {}
        parents: dict[str, dict[str, str]] = {}
        with store_csv.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                uid = (row.get("Tilda UID") or "").strip()
                sku = (row.get("SKU") or "").strip()
                parent = (row.get("Parent UID") or "").strip()
                if not sku and uid:
                    parents[uid] = row
                if sku and parent:
                    by_parent.setdefault(parent, []).append(row)
        # Attach parent title onto groups via key parent uid
        self._csv_parents = parents  # type: ignore[attr-defined]
        return by_parent

    def _create_product_from_page(
        self,
        page: ScrapedPage,
        csv_editions: dict[str, list[dict[str, str]]],
    ) -> tuple[Product | None, int]:
        """Create Product+SKUs for sitemap pages missing from DB (e.g. BV332)."""
        parent_uid: str | None = None
        uid_match = _TPRODUCT_UID.search(page.url)
        if uid_match:
            parent_uid = uid_match.group(1)
        if parent_uid is None:
            for uid, row in self._csv_parents.items():
                url = (row.get("Url") or "").strip()
                path = urlparse(url).path.strip("/")
                if page.slug in path or path.endswith(page.slug):
                    parent_uid = uid
                    break

        editions = csv_editions.get(parent_uid or "", [])
        try:
            category = _ensure_category_for_slug(page.slug)
        except Category.DoesNotExist as exc:
            self.stderr.write(f"  no category for {page.slug}: {exc}")
            return None, 0
        desc = _compose_description(page)

        with transaction.atomic():
            product = Product.objects.create(
                slug=page.slug[:200],
                name=(page.title or page.slug)[:200],
                description=desc,
                category=category,
            )
            created = 0
            if not editions:
                # Prefer series code from slug: sharovoy-kran-bv332 → BV332
                series = page.slug.rsplit("-", maxsplit=1)[-1].upper()[:100]
                SKU.objects.create(
                    product=product,
                    sku_code=series,
                    slug=f"{page.slug}-{slugify(series)}"[:300],
                    name=(page.title or series)[:300],
                    description=desc,
                    is_published=True,
                )
                created = 1
            else:
                for row in editions:
                    code = (row.get("SKU") or "").strip()
                    title = (row.get("Title") or "").strip() or code
                    sku_slug = f"{page.slug}-{slugify(code)}"
                    SKU.objects.update_or_create(
                        sku_code=code,
                        defaults={
                            "product": product,
                            "slug": sku_slug[:300],
                            "name": title[:300],
                            "description": desc,
                            "is_published": True,
                        },
                    )
                    created += 1
        return product, created

    def _attach_images(self, skus: list[SKU], page: ScrapedPage) -> int:
        """Attach page images to SKUs that still have no photo."""
        targets = [sku for sku in skus if not sku.images.filter(is_published=True).exists()]
        if not targets:
            return 0
        added = 0
        for order, url in enumerate(page.image_urls):
            try:
                raw = _download_bytes(url)
                webp = convert_bytes_to_webp(raw, quality=90)
            except (HTTPError, URLError, OSError, ValueError) as exc:
                logger.warning("image skip %s: %s", url, exc)
                continue
            for sku in targets:
                if ProductImage.objects.filter(sku=sku, source_url=url).exists():
                    continue
                img = ProductImage(
                    sku=sku,
                    alt=(page.title or sku.name)[:300],
                    source_url=url,
                    sort_order=order,
                    is_published=True,
                )
                safe_code = slugify(sku.sku_code) or f"sku-{sku.pk}"
                filename = f"{safe_code}-page-{order}.webp"
                img.image.save(filename, ContentFile(webp), save=False)
                img.save()
                added += 1
        return added
