"""Unify catalog PDP ТТХ into DA8MQU-style grouped attribute cards."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.etl.specs_to_attrs import enrich_catalog_cards


class Command(BaseCommand):
    """Parse specs_text → canonical EAV cards; clear duplicate prose."""

    help = (
        "Enrich catalog SKUs: specs_text bullets → grouped attribute cards "
        "(skips canonical series: DA8MQU, all BV* ball valves). "
        "Use --dry-run to preview."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--product",
            dest="product_slug",
            default="",
            help="Limit to Product.slug",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report without writing",
        )

    def handle(self, *args: object, **options: object) -> None:
        product_slug = str(options.get("product_slug") or "").strip() or None
        dry_run = bool(options.get("dry_run"))
        summary = enrich_catalog_cards(
            product_slug=product_slug,
            dry_run=dry_run,
        )
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}catalog cards: total={summary['total']}, "
                f"enriched={summary['enriched']}, skipped={summary['skipped']}, "
                f"cleared_specs={summary['cleared_specs']}, "
                f"avg_attrs={summary['avg_attrs']}",
            ),
        )
        # Show weakest SKUs for follow-up.
        weak = [
            r
            for r in summary["results"]
            if not r.skipped
            and r.attrs_after < 8
            and "bv" not in r.sku_code.lower()
            and "8100" not in r.sku_code.lower()
        ]
        weak.sort(key=lambda r: r.attrs_after)
        for r in weak[:15]:
            self.stdout.write(
                f"  weak {r.sku_code}: attrs={r.attrs_after} slugs={','.join(r.slugs[:8])}",
            )
