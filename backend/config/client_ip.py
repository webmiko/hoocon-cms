"""Client IP behind the trusted reverse proxy (host nginx → gunicorn).

One resolver for axes, DRF throttles and OTP quotas so they agree on who
the caller is. Only the entries appended by our own proxies are trusted:
the leftmost X-Forwarded-For values are whatever the client sent.
"""

from __future__ import annotations

import ipaddress

from django.conf import settings
from django.http import HttpRequest

_FALLBACK = "0.0.0.0"


def trusted_proxy_hops() -> int:
    """Reverse proxies in front of Django that append to X-Forwarded-For."""
    return max(0, int(getattr(settings, "TRUSTED_PROXY_HOPS", 1)))


def _valid(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: HttpRequest) -> str:
    """IP of the peer seen by the outermost trusted proxy."""
    hops = trusted_proxy_hops()
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if hops and parts:
        resolved = _valid(parts[-min(hops, len(parts))])
        if resolved:
            return resolved
    return _valid(request.META.get("REMOTE_ADDR") or "") or _FALLBACK
