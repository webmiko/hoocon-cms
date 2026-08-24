"""Invalidate the short-lived public catalog HTTP response cache."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from catalog.http_cache import catalog_http_cache_ttl, invalidate_catalog_http_cache


class Command(BaseCommand):
    """Bump catalog HTTP cache version (ops / after bulk enrich)."""

    help = (
        "Invalidate Redis/LocMem cache for GET /api/catalog/{categories,facets,skus}. "
        "Prices toggle already invalidates via SiteSettings signal; use this after "
        "bulk enrich if you need an immediate refresh before TTL."
    )

    def handle(self, *args: object, **options: object) -> None:
        """Print new cache version and configured TTL."""
        version = invalidate_catalog_http_cache()
        ttl = catalog_http_cache_ttl()
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalog HTTP cache invalidated (version={version}, ttl={ttl}s).",
            ),
        )
