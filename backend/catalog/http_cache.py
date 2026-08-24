"""Short-lived HTTP response cache for public catalog GET JSON.

Goal: bots and repeat SPA fetches hit Redis (or LocMem in CI) instead of
re-running heavy ``/api/catalog/skus/`` queries. See docs/bot-load-defense.md
phase 0.

Design notes (avoid later bugs):

- Whitelist paths only (not compare / docs zip / file upload).
- Cache key uses a global **version** integer so invalidate is O(1) and safe
  with LocMem (no SCAN/delete_pattern).
- Body is host-agnostic (RelativeImageField) → key is path + sorted query.
- Same payload for anon and staff → no Cookie / Authorization in the key.
- ``SiteSettings.show_prices_on_site`` changes must bump version (signal).
- TTL alone covers ordinary Admin/ETL catalog edits (30s staleness OK).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse

# Bump this string if cached payload shape changes incompatibly.
_CACHE_NS = "catalog:http:v1"
_VERSION_KEY = f"{_CACHE_NS}:ver"

# Exact list endpoints + SKU detail (not …/files/, not compare/docs).
_PATH_RE = re.compile(
    r"^/api/catalog/(?:categories|facets)/?$"
    r"|^/api/catalog/skus/?$"
    r"|^/api/catalog/skus/[^/]+/?$",
)


def catalog_http_cache_ttl() -> int:
    """Seconds to keep a catalog GET; ``0`` disables the cache."""
    return max(0, int(getattr(settings, "CATALOG_HTTP_CACHE_SECONDS", 30)))


def is_catalog_http_cacheable_path(path: str) -> bool:
    """Return True for whitelist GET paths (categories / facets / skus)."""
    return bool(_PATH_RE.match(path or ""))


def normalize_query_string(raw: str) -> str:
    """Sort query pairs so ``?b=1&a=2`` and ``?a=2&b=1`` share one key."""
    if not raw:
        return ""
    pairs = parse_qsl(raw, keep_blank_values=True)
    return urlencode(sorted(pairs))


def catalog_http_cache_version() -> int:
    """Current invalidate epoch (starts at 1)."""
    ver = cache.get(_VERSION_KEY)
    if ver is None:
        cache.add(_VERSION_KEY, 1, timeout=None)
        ver = cache.get(_VERSION_KEY) or 1
    return int(ver)


def invalidate_catalog_http_cache() -> int:
    """Bump version so all prior catalog HTTP keys miss. Returns new version.

    When the epoch key is missing, seed past the implicit initial version (1)
    used by ``catalog_http_cache_version`` — otherwise re-seeding to 1 would
    keep hitting bodies still stored under ``…:1:…`` keys.
    """
    try:
        return int(cache.incr(_VERSION_KEY))
    except ValueError:
        cache.set(_VERSION_KEY, 2, timeout=None)
        return 2


def build_catalog_http_cache_key(path: str, query_string: str) -> str:
    """Stable cache key for path + normalized query + version."""
    qs = normalize_query_string(query_string)
    digest = hashlib.sha256(f"{path}?{qs}".encode()).hexdigest()[:32]
    return f"{_CACHE_NS}:{catalog_http_cache_version()}:{digest}"


def should_attempt_catalog_http_cache(request: HttpRequest) -> bool:
    """True when this request may be served from / written to the cache."""
    if catalog_http_cache_ttl() <= 0:
        return False
    if request.method not in ("GET", "HEAD"):
        return False
    return is_catalog_http_cacheable_path(request.path)


def load_cached_catalog_response(request: HttpRequest) -> HttpResponse | None:
    """Return a cached HttpResponse or None on miss / disabled."""
    if not should_attempt_catalog_http_cache(request):
        return None
    key = build_catalog_http_cache_key(
        request.path,
        request.META.get("QUERY_STRING", ""),
    )
    payload = cache.get(key)
    if not isinstance(payload, dict):
        return None
    body = payload.get("body")
    if not isinstance(body, (bytes, bytearray)):
        return None
    if request.method == "HEAD":
        body = b""
    response = HttpResponse(
        bytes(body),
        status=int(payload.get("status", 200)),
        content_type=str(payload.get("content_type") or "application/json"),
    )
    _apply_cache_headers(response, hit=True)
    return response


def store_catalog_http_response(request: HttpRequest, response: HttpResponse) -> None:
    """Persist a successful JSON response for the catalog whitelist."""
    if not should_attempt_catalog_http_cache(request):
        return
    if request.method != "GET":
        # HEAD is served from the GET entry; do not store empty bodies.
        _apply_cache_headers(response, hit=False)
        return
    if response.status_code != 200:
        return
    # Never cache Set-Cookie (should not happen on public catalog GETs).
    if response.has_header("Set-Cookie"):
        return
    content_type = response.get("Content-Type", "")
    if "application/json" not in content_type:
        return
    try:
        body = response.content
    except Exception:  # noqa: BLE001 — streaming / unrendered
        return
    if not body:
        return
    # Cap accidental huge pages (Redis memory); normal list ≪ this.
    max_bytes = int(getattr(settings, "CATALOG_HTTP_CACHE_MAX_BYTES", 1_048_576))
    if len(body) > max_bytes:
        return
    key = build_catalog_http_cache_key(
        request.path,
        request.META.get("QUERY_STRING", ""),
    )
    cache.set(
        key,
        {
            "body": bytes(body),
            "status": response.status_code,
            "content_type": content_type.split(";")[0].strip() or "application/json",
        },
        timeout=catalog_http_cache_ttl(),
    )
    _apply_cache_headers(response, hit=False)


def _apply_cache_headers(response: HttpResponse, *, hit: bool) -> None:
    """Browser/CDN hint + observability. Public JSON, short TTL."""
    ttl = catalog_http_cache_ttl()
    if ttl > 0:
        response["Cache-Control"] = f"public, max-age={ttl}"
    # Drop Cookie from effective caching story for intermediaries that honor
    # our Cache-Control; body does not vary by session.
    response["Vary"] = "Accept-Encoding"
    response["X-Catalog-Cache"] = "HIT" if hit else "MISS"


def catalog_http_cache_debug_info(request: HttpRequest) -> dict[str, Any]:
    """Small dict for tests / management commands."""
    return {
        "ttl": catalog_http_cache_ttl(),
        "version": catalog_http_cache_version(),
        "path_ok": is_catalog_http_cacheable_path(request.path),
        "key": build_catalog_http_cache_key(
            request.path,
            request.META.get("QUERY_STRING", ""),
        ),
    }
