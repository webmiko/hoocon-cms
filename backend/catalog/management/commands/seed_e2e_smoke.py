"""Minimal published SKU for Playwright smoke tests."""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import SKU, Category, Product


class Command(BaseCommand):
    help = "Seed one published catalog SKU for Playwright smoke tests."

    def handle(self, *args, **options) -> None:
        category, _ = Category.objects.get_or_create(
            slug="vozdushnie",
            defaults={"name": "Воздушные"},
        )
        product, _ = Product.objects.get_or_create(
            slug="hva-e2e",
            defaults={"name": "HVA", "category": category},
        )
        sku, created = SKU.objects.update_or_create(
            slug="privod-hva-5nm",
            defaults={
                "product": product,
                "name": "Привод HVA 5NM",
                "sku_code": "HVA-5NM",
                "price": Decimal("1234.50"),
                "is_published": True,
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} smoke SKU {sku.slug} ({sku.sku_code})"),
        )
