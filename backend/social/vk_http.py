"""VK CDN URL allowlist for inbound attachment downloads (SSRF hardening)."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

from social.max_http import public_urlopen

_VK_ATTACHMENT_HOST_SUFFIXES = (
    ".userapi.com",
    ".vk.com",
    ".vk-cdn.net",
    ".vkuserphoto.ru",
    ".vkuser.net",
    ".mycdn.me",
)
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def vk_attachment_url_allowed(url: str) -> bool:
    """True when URL is HTTPS on a known VK CDN host (not internal / evil)."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host == "localhost":
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        return False
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _VK_ATTACHMENT_HOST_SUFFIXES)


def vk_download_attachment(url: str) -> tuple[bytes, str] | None:
    """Download VK attachment bytes when URL passes allowlist."""
    src = (url or "").strip()
    if not vk_attachment_url_allowed(src):
        return None
    request = Request(src)
    try:
        with public_urlopen(request, timeout=30) as response:
            payload = response.read(_MAX_ATTACHMENT_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    if len(payload) > _MAX_ATTACHMENT_BYTES:
        return None
    name = Path(src.split("?", 1)[0].rstrip("/")).name or "file"
    return payload, name
