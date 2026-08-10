"""Hotlink allowlist helpers for ``/media/`` (Referer host check)."""

from __future__ import annotations

from urllib.parse import urlparse


def host_from_origin_or_url(value: str) -> str | None:
    """Extract hostname from an origin/URL string (lowercase, no port).

    Args:
        value: Absolute URL, origin, or bare hostname.

    Returns:
        Hostname or None when unparsable / empty.
    """
    raw = value.strip()
    if not raw or raw == "*":
        return None
    if "://" not in raw:
        # Bare host or host:port
        raw = f"https://{raw}"
    try:
        host = urlparse(raw).hostname
    except ValueError:
        return None
    if not host:
        return None
    return host.lower()


def build_media_hotlink_hosts(
    *,
    allowed_hosts: list[str],
    cors_origins: list[str],
    extra_hosts: list[str],
) -> frozenset[str]:
    """Union of hostnames allowed to embed / fetch ``/media/``.

    Args:
        allowed_hosts: Django ``ALLOWED_HOSTS`` entries.
        cors_origins: CORS / CSRF trusted origins.
        extra_hosts: Explicit env extras (e.g. staging CNAME).

    Returns:
        Lowercase hostname set (includes localhost helpers).
    """
    hosts: set[str] = {"localhost", "127.0.0.1", "testserver"}
    for item in (*allowed_hosts, *extra_hosts):
        host = host_from_origin_or_url(item)
        if host:
            hosts.add(host)
    for origin in cors_origins:
        host = host_from_origin_or_url(origin)
        if host:
            hosts.add(host)
    return frozenset(hosts)


def referer_allowed_for_media(
    referer: str | None,
    *,
    allowed_hosts: frozenset[str],
    allow_empty: bool,
) -> bool:
    """Return True when the Referer may load a media asset.

    Empty / missing Referer is allowed when ``allow_empty`` (direct tab, mail
    clients). Foreign sites send their own Referer and are denied.

    Args:
        referer: Raw ``Referer`` header value.
        allowed_hosts: Allowlisted hostnames.
        allow_empty: Permit requests with no Referer.

    Returns:
        Whether the request should proceed.
    """
    if referer is None or not referer.strip():
        return allow_empty

    host = host_from_origin_or_url(referer)
    if host is None:
        return allow_empty

    if host in allowed_hosts:
        return True

    # Allow subdomains of an allowlisted apex (e.g. www / cdn).
    for allowed in allowed_hosts:
        if host == allowed or host.endswith(f".{allowed}"):
            return True

    return False
