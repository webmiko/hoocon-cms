"""Re-fetch product pages and split Tilda tabs into product / SKU fields.

Model pages (Описание / Инструкция / Характеристики / Аналоги) → Product +
scoped SKU. Optional category mirror for short family overviews.
"""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.html_text import (
    ensure_safety_in_instructions,
    extract_safety_notice,
    extract_tilda_tabs,
    filter_analogs_for_sku,
    html_to_text,
)
from catalog.etl.instruction_style import normalize_instruction_style
from catalog.etl.sku_variant import (
    filter_description_for_variant,
    parse_sku_variant,
    rewrite_series_tokens_for_variant,
)
from catalog.etl.tech_copy import MANUAL_SAFETY_ATTENTION_LINES, normalize_tech_copy
from catalog.models import SKU, Product

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; HooconCMS/1.0; +https://hoocon.ru; product-sections)"
_BASE = "https://hoocon.ru"

# Live Tilda slug typos / redirects that differ from CMS Product.slug.
_LIVE_SLUG_ALIASES: dict[str, str] = {
    "privod-protivopozharniy-3nm": "privod-protivipozharniy-3nm",
}

_TYPO_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)Техгические"), "Технические"),
    (re.compile(r"(?i)харктеристик"), "характеристик"),
    # Tilda footnote asterisk after a label: «Площадь заслонки: *»
    (re.compile(r":\s*\*\s*(?=\n|$)"), ":\n"),
    (re.compile(r":\s*\*\s+"), ": "),
)


class Command(BaseCommand):
    """Populate product/SKU section fields from live Tilda pages."""

    help = (
        "Fetch product pages and split Описание/Инструкция/Характеристики/Аналоги "
        "into product and SKU fields (with style normalization)"
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
        parser.add_argument(
            "--prefix",
            default="",
            help="Only products whose slug starts with this prefix",
        )
        parser.add_argument(
            "--no-category",
            action="store_true",
            help="Do not mirror description/instructions onto the Category",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        limit = int(options["limit"] or 0)
        only = str(options["slug"] or "").strip()
        prefix = str(options["prefix"] or "").strip()
        no_category = bool(options["no_category"])

        qs = Product.objects.select_related("category").order_by("slug")
        if only:
            qs = qs.filter(slug=only)
        if prefix:
            qs = qs.filter(slug__startswith=prefix)
        if limit > 0:
            qs = qs[:limit]

        ok = skip = 0
        for product in qs:
            try:
                changed = self._process_product(
                    product,
                    dry_run=dry_run,
                    no_category=no_category,
                )
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

    def _process_product(
        self,
        product: Product,
        *,
        dry_run: bool,
        no_category: bool,
    ) -> bool:
        """Fetch one product page and distribute section fields."""
        url = live_url_for_product_slug(product.slug)
        html = _fetch(url)
        tabs = extract_tilda_tabs(html)
        if not tabs:
            return False

        meta = _meta_description(html)
        description = _normalize_copy(tabs.get("description", ""))
        instructions = _normalize_instructions(tabs.get("instructions", ""))
        safety = extract_safety_notice(html)
        if not safety:
            safety = "\n".join(MANUAL_SAFETY_ATTENTION_LINES)
        instructions = ensure_safety_in_instructions(instructions, safety)
        instructions = _normalize_instructions(instructions)
        specs = _normalize_copy(tabs.get("specs", ""))
        analogs = _normalize_copy(tabs.get("analogs", ""))

        if dry_run:
            self.stdout.write(
                f"    url={url} tabs={sorted(tabs)} "
                f"desc={len(description)} inst={len(instructions)} "
                f"specs={len(specs)} analogs={len(analogs)} "
                f"safety={'yes' if safety else 'no'}",
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

            if not no_category:
                category = product.category
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


def live_url_for_product_slug(slug: str) -> str:
    """Resolve CMS product slug to the live hoocon.ru path."""
    live = _LIVE_SLUG_ALIASES.get(slug, slug)
    return f"{_BASE}/{live}"


def _normalize_copy(text: str) -> str:
    """Apply Belimo RU / typo cleanup to a tab body."""
    out = normalize_tech_copy(text or "")
    for pattern, repl in _TYPO_FIXES:
        out = pattern.sub(repl, out)
    return out.strip()


def _normalize_instructions(text: str) -> str:
    """Instruction-tab layout + Belimo RU wording."""
    return normalize_instruction_style(_normalize_copy(text))


def _fetch(url: str, *, timeout: float = 45.0) -> str:
    """GET HTML from hoocon.ru product page."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", "replace")


def _meta_description(page_html: str) -> str:
    """Read og:description / meta description as the card lead."""
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
