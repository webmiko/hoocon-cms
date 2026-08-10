"""Remap typo product/SKU slugs to canonical paths (SEO URL migration)."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.etl.normalize import PRODUCT_SLUG_REMAP
from catalog.models import SKU, Product
from redirects.models import Redirect


class Command(BaseCommand):
    """Rename products/SKUs whose slug still uses a known Tilda typo."""

    help = (
        "Apply PRODUCT_SLUG_REMAP to Product.slug and dependent SKU.slug "
        "(prefix replace), and seed 301 Redirect rows for old paths. "
        "Use --dry-run to preview."
    )

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report renames without writing",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run"))
        renamed_products = 0
        renamed_skus = 0
        redirects = 0
        with transaction.atomic():
            for typo, canonical in PRODUCT_SLUG_REMAP.items():
                product = Product.objects.filter(slug=typo).first()
                if product is None:
                    # Already remapped — still ensure redirects exist.
                    product = Product.objects.filter(slug=canonical).first()
                    if product is not None:
                        redirects += self._ensure_redirects(
                            typo,
                            canonical,
                            product,
                            dry_run=dry_run,
                        )
                    continue
                if Product.objects.filter(slug=canonical).exclude(pk=product.pk).exists():
                    self.stderr.write(
                        self.style.ERROR(
                            f"skip {typo}: target {canonical} already exists",
                        ),
                    )
                    continue
                self.stdout.write(f"  product {typo} → {canonical}")
                if not dry_run:
                    product.slug = canonical
                    product.save(update_fields=["slug"])
                renamed_products += 1
                for sku in SKU.objects.filter(product=product):
                    old = sku.slug
                    if old.startswith(f"{typo}-"):
                        new = f"{canonical}-{old[len(typo) + 1 :]}"
                    elif old == typo:
                        new = canonical
                    else:
                        continue
                    if SKU.objects.filter(slug=new).exclude(pk=sku.pk).exists():
                        self.stderr.write(
                            self.style.ERROR(f"skip sku {old}: {new} exists"),
                        )
                        continue
                    self.stdout.write(f"    sku {old} → {new}")
                    if not dry_run:
                        sku.slug = new
                        sku.save(update_fields=["slug"])
                    renamed_skus += 1
                redirects += self._ensure_redirects(
                    typo,
                    canonical,
                    product,
                    dry_run=dry_run,
                )
            if dry_run:
                transaction.set_rollback(True)
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}slug remap: products={renamed_products}, skus={renamed_skus}, redirects={redirects}",
            ),
        )

    def _ensure_redirects(
        self,
        typo: str,
        canonical: str,
        product: Product,
        *,
        dry_run: bool,
    ) -> int:
        """Create/update 301 rows for product + edition paths."""
        count = 0
        pairs = [(f"/{typo}", f"/{canonical}")]
        for sku in SKU.objects.filter(product=product):
            if not sku.slug.startswith(f"{canonical}-"):
                continue
            suffix = sku.slug[len(canonical) + 1 :]
            pairs.append((f"/{typo}-{suffix}", f"/{sku.slug}"))
        for from_path, to_path in pairs:
            self.stdout.write(f"  redirect {from_path} → {to_path}")
            if not dry_run:
                Redirect.objects.update_or_create(
                    from_path=from_path,
                    defaults={
                        "to_path": to_path,
                        "status_code": 301,
                        "is_active": True,
                    },
                )
            count += 1
        return count
