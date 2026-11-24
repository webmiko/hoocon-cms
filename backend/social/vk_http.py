"""VK CDN URL allowlist for inbound attachment downloads (SSRF hardening)."""

from __future__ import annotations

import ipaddress
import logging
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request

from social.max_http import public_urlopen_checked

logger = logging.getLogger("hoocon.social")

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
    # urlparse and the HTTP client disagree on «host\\@allowed.host» and similar;
    # real CDN links never carry userinfo, backslashes or a custom port.
    if "\\" in (url or "") or "@" in parsed.netloc:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in (None, 443):
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


def vk_download_attachment(url: str, *, max_bytes: int | None = None) -> tuple[bytes, str] | None:
    """Download VK attachment bytes when URL passes allowlist (redirects too)."""
    src = (url or "").strip()
    host = (urlparse(src).hostname or "")[:80]
    if not vk_attachment_url_allowed(src):
        logger.warning("vk_attachment_host_rejected host=%s", host)
        return None
    limit = max_bytes if max_bytes is not None else _MAX_ATTACHMENT_BYTES
    request = Request(src)
    try:
        with public_urlopen_checked(request, allowed=vk_attachment_url_allowed, timeout=30) as response:
            payload = response.read(limit + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("vk_attachment_download_failed host=%s error=%s", host, type(exc).__name__)
        return None
    if len(payload) > limit:
        logger.warning("vk_attachment_too_big host=%s limit=%s", host, limit)
        return None
    name = Path(src.split("?", 1)[0].rstrip("/")).name or "file"
    return payload, name
