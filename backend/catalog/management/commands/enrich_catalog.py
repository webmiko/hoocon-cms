"""Enrich catalog from Tilda JSON + store CSV + live sitemap scan.

Fills missing products (slug map for empty buttonlink), SKU descriptions,
product characteristics as EAV, better edition titles from store CSV,
and optionally og:description from live product pages.

Usage:
  poetry run python manage.py enrich_catalog \\
    --source ../hoocon/data/hoocon_catalog_api.json \\
    --store-csv ~/Downloads/store-….csv \\
    --scan-site
"""

from __future__ import annotations

import csv
import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.etl.extract import extract_categories, extract_products
from catalog.etl.html_text import html_to_text
from catalog.etl.load import LoadStats, load_categories, load_product
from catalog.etl.normalize import QuarantineError, normalize_category, normalize_product
from catalog.etl.quarantine import write_quarantine_csv
from catalog.etl.slug_map import apply_slug_to_product, build_uid_slug_map
from catalog.models import SKU

logger = logging.getLogger(__name__)

USER_AGENT = "HooconCMS-CatalogEnrich/1.0 (+https://hoocon.ru)"
SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_OG_DESC = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_META_DESC = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve().parent


def _default_seed() -> Path:
    return _repo_root() / "docs" / "redirects-tproduct-seed.csv"


def _fetch_text(url: str, timeout: int = 25) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — allowlisted hosts
        return resp.read().decode("utf-8", errors="replace")


def _sitemap_product_urls(local_fallback: Path | None = None) -> list[str]:
    """Collect product-like URLs from live or local sitemap."""
    urls: list[str] = []
    try:
        xml = _fetch_text("https://hoocon.ru/sitemap.xml")
        root = ET.fromstring(xml)
        urls = [e.text.strip() for e in root.findall(".//s:loc", SITEMAP_NS) if e.text]
    except (HTTPError, URLError, ET.ParseError, OSError) as exc:
        logger.warning("Live sitemap failed: %s", exc)
        if local_fallback and local_fallback.is_file():
            root = ET.parse(local_fallback).getroot()
            urls = [e.text.strip() for e in root.findall(".//s:loc", SITEMAP_NS) if e.text]

    product_re = re.compile(
        r"privod|sharov|kran|zaslon|dimoudal|protivopozhar|tproduct",
        re.I,
    )
    return sorted({u for u in urls if product_re.search(u or "")})


def _extract_page_description(html: str) -> str:
    for pattern in (_OG_DESC, _META_DESC):
        match = pattern.search(html)
        if match:
            return html_to_text(match.group(1))
    return ""


def _load_csv_titles(store_csv: Path) -> dict[str, str]:
    """sku_code.lower() → Title from store CSV edition rows."""
    titles: dict[str, str] = {}
    with store_csv.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            code = (row.get("SKU") or "").strip()
            title = (row.get("Title") or "").strip()
            if code and title:
                titles[code.lower()] = title
    return titles


class Command(BaseCommand):
    """Scan sources and enrich catalog product cards."""

    help = "Enrich catalog from JSON + CSV + optional live sitemap scan"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--source",
            default=str(_repo_root().parent / "hoocon" / "data" / "hoocon_catalog_api.json"),
            help="Path to hoocon_catalog_api.json",
        )
        parser.add_argument(
            "--store-csv",
            default="",
            help="Tilda store CSV (Titles + Photos).",
        )
        parser.add_argument(
            "--seed-csv",
            default=str(_default_seed()),
            help="redirects-tproduct-seed.csv for missing buttonlink",
        )
        parser.add_argument(
            "--quarantine",
            default="reports/quarantine_enrich.csv",
            help="Quarantine CSV path",
        )
        parser.add_argument(
            "--scan-site",
            action="store_true",
            help="Fetch sitemap product pages and fill short og:description gaps",
        )
        parser.add_argument(
            "--sitemap-local",
            default=str(_repo_root().parent / "hoocon" / "tilda" / "sitemap.xml"),
            help="Fallback local sitemap.xml",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source_path = Path(options["source"]).expanduser().resolve()
        if not source_path.is_file():
            raise CommandError(f"Source not found: {source_path}")

        seed_csv = Path(options["seed_csv"]).expanduser().resolve()
        store_csv_opt = (options.get("store_csv") or "").strip()
        store_csv = Path(store_csv_opt).expanduser().resolve() if store_csv_opt else None
        if store_csv is None:
            # Try the Downloads export used earlier in the session.
            candidate = Path.home() / "Downloads" / "store-12190035-202607191843.csv"
            if candidate.is_file():
                store_csv = candidate

        uid_slug_map = build_uid_slug_map(seed_csv=seed_csv, store_csv=store_csv)
        self.stdout.write(f"Slug map entries: {len(uid_slug_map)}")

        payload = json.loads(source_path.read_text(encoding="utf-8"))
        quarantined: list[dict[str, Any]] = []

        cat_norm = []
        for cid, name, parent_id in extract_categories(payload):
            try:
                cat_norm.append(normalize_category(cid=cid, name=name, parent_id=parent_id))
            except QuarantineError as exc:
                quarantined.append({"reason": exc.reason, "payload": exc.payload})

        cat_stats, cat_map, cat_q = load_categories(cat_norm)
        quarantined.extend(cat_q)

        prod_stats = LoadStats()
        loaded_slugs: list[str] = []
        for raw_product in extract_products(payload):
            patched = apply_slug_to_product(raw_product, uid_slug_map)
            try:
                np = normalize_product(patched)
            except QuarantineError as exc:
                quarantined.append({"reason": exc.reason, "payload": exc.payload})
                continue
            try:
                ps = load_product(np, category_map=cat_map)
                prod_stats.products_created += ps.products_created
                prod_stats.skus_created += ps.skus_created
                prod_stats.attribute_values_created += ps.attribute_values_created
                loaded_slugs.append(np.slug)
            except QuarantineError as exc:
                quarantined.append({"reason": exc.reason, "payload": exc.payload})

        titles_updated = 0
        if store_csv and store_csv.is_file():
            titles = _load_csv_titles(store_csv)
            for sku in SKU.objects.all().only("id", "sku_code", "name"):
                better = titles.get(sku.sku_code.lower())
                if better and better != sku.name:
                    sku.name = better[:300]
                    sku.save(update_fields=["name"])
                    titles_updated += 1

        site_updated = 0
        if options["scan_site"]:
            site_updated = self._scan_site(
                Path(options["sitemap_local"]),
            )

        written = write_quarantine_csv(quarantined, Path(options["quarantine"]))

        with_desc = SKU.objects.exclude(description="").count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Enrich done: cats +{cat_stats.created}, "
                f"products +{prod_stats.products_created}, "
                f"skus +{prod_stats.skus_created}, "
                f"attrs +{prod_stats.attribute_values_created}, "
                f"titles_updated={titles_updated}, "
                f"site_desc_updated={site_updated}, "
                f"skus_with_description={with_desc}/{SKU.objects.count()}, "
                f"quarantined={written}, "
                f"product_slugs={len(loaded_slugs)}",
            ),
        )

    def _scan_site(self, local_sitemap: Path) -> int:
        """Fetch product pages; fill empty/short SKU descriptions from og:description."""
        urls = _sitemap_product_urls(local_sitemap)
        self.stdout.write(f"Sitemap product URLs: {len(urls)}")
        updated = 0
        for url in urls:
            slug = urlparse(url).path.strip("/")
            if not slug or slug.startswith("tproduct"):
                continue
            try:
                html = _fetch_text(url)
            except (HTTPError, URLError, OSError, TimeoutError) as exc:
                self.stderr.write(f"  fetch fail {url}: {exc}")
                continue
            desc = _extract_page_description(html)
            if not desc:
                time.sleep(0.15)
                continue
            # Match SKUs whose slug starts with product path or equals product slug prefix
            qs = SKU.objects.filter(product__slug=slug)
            if not qs.exists():
                qs = SKU.objects.filter(slug__startswith=f"{slug}-")
            for sku in qs:
                if not sku.description or len(sku.description) < len(desc):
                    # Prefer longer structured JSON descr; only fill gaps.
                    if not sku.description:
                        sku.description = desc
                        sku.save(update_fields=["description"])
                        updated += 1
            time.sleep(0.2)
            self.stdout.write(f"  scanned {slug}")
        return updated
