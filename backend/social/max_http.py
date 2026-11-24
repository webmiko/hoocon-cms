"""HTTP helpers for MAX Bot API (platform-api2.max.ru)."""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import ssl
import uuid
from collections.abc import Callable
from http.client import HTTPResponse
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

from django.conf import settings

_MAX_API = "https://platform-api2.max.ru"
_HTTP_TIMEOUT_SEC = 30
# Built-in MAX CDN suffixes; ``MAX_ATTACHMENT_EXTRA_HOSTS`` (env) adds more.
# ``.oneme.ru`` serves MAX images (``i.oneme.ru``); add video/file hosts from
# the ``max_attachment_received`` log lines once confirmed on production.
_MAX_ATTACHMENT_HOST_SUFFIXES = (".max.ru", ".oneme.ru")


def max_attachment_host_suffixes() -> tuple[str, ...]:
    """Allowed host suffixes: built-in list plus ``MAX_ATTACHMENT_EXTRA_HOSTS``."""
    extra = tuple(getattr(settings, "MAX_ATTACHMENT_EXTRA_HOSTS", ()) or ())
    return _MAX_ATTACHMENT_HOST_SUFFIXES + extra


def max_attachment_url_allowed(url: str) -> bool:
    """True when a MAX inbound attachment URL is an allowed public HTTPS host."""
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
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in max_attachment_host_suffixes())


_CA_BUNDLE = Path(settings.BASE_DIR) / "certs" / "max-ca-bundle.pem"


def max_api_base() -> str:
    """MAX Bot API host."""
    return _MAX_API


def max_ssl_context() -> ssl.SSLContext:
    """SSL context with Russian Trusted CA bundle when bundled in repo."""
    if _CA_BUNDLE.is_file():
        return ssl.create_default_context(cafile=str(_CA_BUNDLE))
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _default_ssl_context() -> ssl.SSLContext:
    """Public CDN / upload hosts (not platform-api2)."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def max_urlopen(request: Request, *, timeout: float = _HTTP_TIMEOUT_SEC) -> HTTPResponse:
    """Open MAX API request with project CA bundle."""
    return urlopen(request, timeout=timeout, context=max_ssl_context())  # noqa: S310


def public_urlopen(request: Request, *, timeout: float = _HTTP_TIMEOUT_SEC) -> HTTPResponse:
    """Open non-MAX hosts (upload CDN) with default public CAs."""
    return urlopen(request, timeout=timeout, context=_default_ssl_context())  # noqa: S310


class _AllowlistRedirectHandler(HTTPRedirectHandler):
    """Follow redirects only to URLs the allowlist accepts (SSRF guard)."""

    def __init__(self, allowed: Callable[[str], bool]) -> None:
        self._allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not self._allowed(newurl):
            raise HTTPError(newurl, code, "redirect target not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def public_urlopen_checked(
    request: Request,
    *,
    allowed: Callable[[str], bool],
    timeout: float = _HTTP_TIMEOUT_SEC,
) -> HTTPResponse:
    """Like ``public_urlopen`` but every redirect hop must pass ``allowed``."""
    opener = build_opener(
        HTTPSHandler(context=_default_ssl_context()),
        _AllowlistRedirectHandler(allowed),
    )
    return opener.open(request, timeout=timeout)  # type: ignore[no-any-return]


def _parse_json_dict(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw[:500]}
    if not isinstance(data, dict):
        return {"raw": data}
    return data


def max_json_request(
    method: str,
    path: str,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
    query: str = "",
) -> tuple[int, dict[str, Any]]:
    """Call MAX API and return HTTP status + JSON body."""
    url = f"{_MAX_API}{path}"
    if query:
        url = f"{url}?{query.lstrip('?')}"
    headers = {"Authorization": token, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method.upper())
    try:
        with max_urlopen(request) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except (URLError, TimeoutError, OSError) as exc:
        raise exc
    return status, _parse_json_dict(raw)


def max_upload_image(token: str, image_path: Path) -> str:
    """Upload local image via POST /uploads; return attachment token."""
    if not image_path.is_file():
        raise FileNotFoundError(str(image_path))
    status, init = max_json_request("POST", "/uploads", token, query="type=image")
    if status >= 400:
        raise RuntimeError(f"MAX /uploads failed: HTTP {status} {init!r}")
    upload_url = str(init.get("url") or "").strip()
    if not upload_url:
        raise RuntimeError(f"MAX /uploads missing url: {init!r}")

    mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    body = image_path.read_bytes()
    boundary = f"----HooconMax{uuid.uuid4().hex}"
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="data"; filename="{image_path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        body,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    upload_body = b"".join(parts)
    upload_req = Request(
        upload_url,
        data=upload_body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with public_urlopen(upload_req) as response:
        raw = response.read().decode("utf-8", errors="replace")
    upload_data = _parse_json_dict(raw)
    upload_token = str(upload_data.get("token") or init.get("token") or "").strip()
    if not upload_token:
        photos = upload_data.get("photos")
        if isinstance(photos, dict):
            for item in photos.values():
                if isinstance(item, dict):
                    upload_token = str(item.get("token") or "").strip()
                    if upload_token:
                        break
    if not upload_token:
        raise RuntimeError(f"MAX image upload missing token: {upload_data!r}")
    return upload_token


def max_message_mid(data: dict[str, Any]) -> str:
    """Extract Message.body.mid from POST /messages response."""
    message = data.get("message")
    if not isinstance(message, dict):
        return ""
    body = message.get("body")
    if isinstance(body, dict):
        mid = str(body.get("mid") or "").strip()
        if mid:
            return mid
    return str(message.get("id") or "").strip()
