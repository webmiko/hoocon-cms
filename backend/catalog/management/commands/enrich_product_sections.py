"""Re-fetch product pages and split Tilda tabs into category vs SKU fields.

General series copy (Описание / Инструкция) → Category.
Model-specific (lead, Характеристики, Аналоги) → Product + scoped SKU.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.html_text import (
    extract_tilda_tabs,
    filter_analogs_for_sku,
    html_to_text,
)
from catalog.etl.sku_variant import (
    filter_description_for_variant,
    parse_sku_variant,
    rewrite_series_tokens_for_variant,
)
from catalog.models import SKU, Product

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; HooconCMS/1.0; +https://hoocon.ru; product-sections)"
_BASE = "https://hoocon.ru"


class Command(BaseCommand):
    """Populate category/product/SKU section fields from live Tilda pages."""

    help = (
        "Fetch product pages and split Описание/Инструкция/Характеристики/Аналоги "
        "into category (general) and SKU (model) fields"
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse only, no DB writes",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max products to process (0 = all)",
        )
        parser.add_argument(
            "--slug",
            default="",
            help="Process a single product slug",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        limit = int(options["limit"] or 0)
        only = str(options["slug"] or "").strip()

        qs = Product.objects.select_related("category").order_by("slug")
        if only:
            qs = qs.filter(slug=only)
        if limit > 0:
            qs = qs[:limit]

        ok = skip = 0
        for product in qs:
            try:
                changed = self._process_product(product, dry_run=dry_run)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                self.stderr.write(f"  fail {product.slug}: {exc}")
                skip += 1
                continue
            if changed:
                ok += 1
                self.stdout.write(f"  ok {product.slug}")
            else:
                skip += 1
                self.stdout.write(f"  skip {product.slug} (no tabs)")

        self.stdout.write(
            self.style.SUCCESS(f"updated={ok} skipped={skip} dry_run={dry_run}"),
        )

    def _process_product(self, product: Product, *, dry_run: bool) -> bool:
        """Fetch one product page and distribute section fields."""
        url = f"{_BASE}/{product.slug}"
        html = _fetch(url)
        tabs = extract_tilda_tabs(html)
        if not tabs:
            return False

        meta = _meta_description(html)
        description = tabs.get("description", "")
        instructions = tabs.get("instructions", "")
        specs = tabs.get("specs", "")
        analogs = tabs.get("analogs", "")

        if dry_run:
            self.stdout.write(
                f"    tabs={sorted(tabs)} "
                f"desc={len(description)} inst={len(instructions)} "
                f"specs={len(specs)} analogs={len(analogs)}",
            )
            return True

        with transaction.atomic():
            product.description = description or product.description
            product.instructions = instructions
            product.specs_text = specs
            product.analogs_text = analogs
            product.save(
                update_fields=[
                    "description",
                    "instructions",
                    "specs_text",
                    "analogs_text",
                    "updated_at",
                ],
            )

            category = product.category
            # Prefer the longest series overview / install guide in the family.
            cat_changed = False
            if description and len(description) >= len(category.description or ""):
                category.description = description
                cat_changed = True
            if instructions and len(instructions) >= len(category.instructions or ""):
                category.instructions = instructions
                cat_changed = True
            if cat_changed:
                category.save(
                    update_fields=["description", "instructions", "updated_at"],
                )

            for sku in SKU.objects.filter(product=product):
                self._apply_sku(
                    sku,
                    meta=meta,
                    description=description,
                    specs=specs,
                    analogs=analogs,
                )
        return True

    def _apply_sku(
        self,
        sku: SKU,
        *,
        meta: str,
        description: str,
        specs: str,
        analogs: str,
    ) -> None:
        """Write model-specific scoped sections onto one SKU."""
        variant = parse_sku_variant(sku.sku_code)
        # Card description: short meta lead + scoped series overview bits.
        lead = meta.strip()
        body_parts = [p for p in (lead, description) if p]
        raw_desc = "\n\n".join(body_parts)
        sku.description = filter_description_for_variant(raw_desc, variant)
        sku.specs_text = filter_description_for_variant(specs, variant)
        sku.specs_text = rewrite_series_tokens_for_variant(sku.specs_text, variant)
        sku.analogs_text = filter_analogs_for_sku(analogs, sku.sku_code)
        sku.analogs_text = rewrite_series_tokens_for_variant(
            sku.analogs_text,
            variant,
        )
        sku.save(
            update_fields=[
                "description",
                "specs_text",
                "analogs_text",
                "updated_at",
            ],
        )


def _fetch(url: str, *, timeout: float = 45.0) -> str:
    """GET HTML from hoocon.ru product page."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _meta_description(page_html: str) -> str:
    """Read og:description / meta description as the card lead."""
    import re

    for pattern in (
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
    ):
        match = re.search(pattern, page_html, re.I)
        if match:
            return html_to_text(match.group(1)).strip()
    return ""
