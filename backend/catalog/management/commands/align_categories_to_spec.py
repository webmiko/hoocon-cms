"""Align catalog categories to the HOOCON model-series specification."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import SKU, Category, Product
from catalog.series_categories import (
    SpecCategory,
    allowed_slugs,
    classify_series_category,
    spec_categories,
)

# Local test junk left from earlier scrapes / manual checks.
_TEST_PRODUCT_SLUGS = frozenset({"hva-test"})


class Command(BaseCommand):
    """Ensure only specification categories exist; reassign products."""

    help = "Keep categories from the series specification only; reassign products by SKU series; delete extras"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print plan without writing",
        )
        parser.add_argument(
            "--drop-ball-valves",
            action="store_true",
            help="Do not keep the Шаровые краны bucket (BV products blocked)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options["dry_run"])
        include_bv = not bool(options["drop_ball_valves"])
        specs = spec_categories(include_ball_valves=include_bv)
        allowed = allowed_slugs(include_ball_valves=include_bv)

        with transaction.atomic():
            by_slug = self._ensure_spec_categories(specs, dry_run=dry_run)
            moved = self._reassign_products(
                by_slug,
                allowed=allowed,
                dry_run=dry_run,
            )
            deleted_products = self._delete_test_products(dry_run=dry_run)
            deleted_cats = self._delete_extra_categories(allowed=allowed, dry_run=dry_run)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"spec categories={len(specs)} moved={moved} "
                f"deleted_products={deleted_products} deleted_categories={deleted_cats} "
                f"dry_run={dry_run}",
            ),
        )

    def _ensure_spec_categories(
        self,
        specs: list[SpecCategory],
        *,
        dry_run: bool,
    ) -> dict[str, Category]:
        """Create/rename canonical categories; clear parent links."""
        by_slug: dict[str, Category] = {}
        for spec in specs:
            cat = Category.objects.filter(slug=spec.slug).first()
            if cat is None:
                self.stdout.write(f"  create {spec.slug}")
                if not dry_run:
                    cat = Category.objects.create(
                        slug=spec.slug,
                        name=spec.name,
                        parent=None,
                    )
                else:
                    cat = Category(slug=spec.slug, name=spec.name)
            else:
                changed = cat.name != spec.name or cat.parent_id is not None
                if changed:
                    self.stdout.write(f"  update {spec.slug} → {spec.name}")
                    if not dry_run:
                        cat.name = spec.name
                        cat.parent = None
                        cat.save(update_fields=["name", "parent", "updated_at"])
            by_slug[spec.slug] = cat
        return by_slug

    def _reassign_products(
        self,
        by_slug: dict[str, Category],
        *,
        allowed: frozenset[str],
        dry_run: bool,
    ) -> int:
        """Move each product into its series category."""
        moved = 0
        for product in Product.objects.select_related("category").iterator():
            if product.slug in _TEST_PRODUCT_SLUGS:
                continue
            codes = list(
                SKU.objects.filter(product=product).values_list("sku_code", flat=True),
            )
            target_slug = classify_series_category(product.slug, codes)
            if target_slug not in allowed:
                self.stderr.write(
                    f"  skip {product.slug}: target {target_slug} not allowed",
                )
                continue
            target = by_slug.get(target_slug)
            if target is None:
                continue
            if product.category_id and product.category.slug == target_slug:
                continue
            self.stdout.write(
                f"  move {product.slug}: {product.category.slug if product.category_id else '—'} → {target_slug}",
            )
            if not dry_run and getattr(target, "pk", None) is not None:
                product.category = target
                product.save(update_fields=["category", "updated_at"])
            moved += 1
        return moved

    def _delete_test_products(self, *, dry_run: bool) -> int:
        """Remove local test products that are not part of the catalog."""
        qs = Product.objects.filter(slug__in=_TEST_PRODUCT_SLUGS)
        count = qs.count()
        for product in qs:
            sku_n = SKU.objects.filter(product=product).count()
            self.stdout.write(f"  delete product {product.slug} (skus={sku_n})")
            if not dry_run:
                SKU.objects.filter(product=product).delete()
                product.delete()
        return count

    def _delete_extra_categories(
        self,
        *,
        allowed: frozenset[str],
        dry_run: bool,
    ) -> int:
        """Delete categories outside the specification (must be empty)."""
        deleted = 0
        for cat in Category.objects.exclude(slug__in=allowed).order_by("slug"):
            n = cat.products.count()
            if n:
                self.stderr.write(
                    f"  cannot delete {cat.slug}: still has {n} product(s)",
                )
                continue
            self.stdout.write(f"  delete category {cat.slug}")
            if not dry_run:
                cat.delete()
            deleted += 1
        return deleted
