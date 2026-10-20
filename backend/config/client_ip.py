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


def rate_limit_subject(ip: str | None) -> str:
    """Bucket for limits: the IPv4 address, or the IPv6 /64 it belongs to.

    Privacy extensions and a hostile /64 rotate the host part. Axes, DRF
    and OTP quotas must share one bucket or the limit is one request per
    address. Analytics keeps the full address from :func:`client_ip`.
    """
    text = (ip or "").strip()
    if not text:
        return _FALLBACK
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return text
    if isinstance(addr, ipaddress.IPv6Address):
        network = ipaddress.ip_network(f"{addr}/64", strict=False)
        return str(network.network_address)
    return str(addr)


def client_rate_key(request: HttpRequest) -> str:
    """Rate-limit identity for this request (axes and OTP)."""
    return rate_limit_subject(client_ip(request))


def install_rate_limit_identity() -> None:
    """Fold IPv6 /64 into every DRF throttle.

    Views construct ``ScopedRateThrottle`` themselves, and DRF has no
    setting for the ident function. Patching the base class covers anon,
    user and scoped limits without editing each view.
    """
    from rest_framework.request import Request
    from rest_framework.throttling import SimpleRateThrottle

    current = SimpleRateThrottle.get_ident
    if getattr(current, "_hoocon_rate_limit", False):
        return
    original = current

    def get_ident(self: SimpleRateThrottle, request: Request) -> str:
        ident = original(self, request)
        return rate_limit_subject(ident if isinstance(ident, str) else None)

    get_ident._hoocon_rate_limit = True  # type: ignore[attr-defined]
    SimpleRateThrottle.get_ident = get_ident  # type: ignore[assignment]
