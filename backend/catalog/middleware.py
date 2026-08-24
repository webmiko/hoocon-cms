"""Middleware: short Redis/LocMem cache for public catalog GET JSON."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from catalog.http_cache import (
    load_cached_catalog_response,
    should_attempt_catalog_http_cache,
    store_catalog_http_response,
)


class CatalogHttpCacheMiddleware:
    """Serve/store whitelist ``/api/catalog/{categories,facets,skus}`` GETs.

    Placed inside the middleware stack so CSP and security headers still wrap
    cached responses. On HIT the view (and DRF throttle increment for that
    path) is skipped — intentional under bot load.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        """Bind the next middleware / view."""
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Return cached body on HIT; otherwise call through and maybe store."""
        if should_attempt_catalog_http_cache(request):
            cached = load_cached_catalog_response(request)
            if cached is not None:
                return cached

        response = self.get_response(request)

        if should_attempt_catalog_http_cache(request):
            store_catalog_http_response(request, response)

        return response
