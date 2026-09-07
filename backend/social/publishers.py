"""HTTP publishers for Telegram, VK and MAX (stdlib urllib)."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPResponse
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from django.conf import settings

from sitesettings.credentials import max_bot_token, telegram_bot_token, vk_access_token

logger = logging.getLogger("hoocon.social")

_HTTP_TIMEOUT_SEC = 20
# Shorter per-attempt timeout + retries: VPS→Telegram often stalls ~20s then fails.
_TELEGRAM_TIMEOUT_SEC = 8
_TELEGRAM_RETRIES = 3
# workers.dev blocks default Python-urllib UA (Cloudflare error 1010).
_TELEGRAM_USER_AGENT = "HooconCMS/1.12 (+https://hoocon.ru)"

UrlOpenFn = Callable[..., HTTPResponse]


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one channel publish call."""

    ok: bool
    external_id: str = ""
    error: str = ""
    skipped: bool = False


def telegram_api_base() -> str:
    """Bot API host (default ``https://api.telegram.org``).

    Set ``TELEGRAM_API_BASE`` to a Cloudflare Worker / reverse proxy when the
    VPS cannot reach ``api.telegram.org`` reliably (e.g. reg.ru MSK egress).
    """
    base = (getattr(settings, "TELEGRAM_API_BASE", "") or "").strip()
    if not base:
        base = "https://api.telegram.org"
    return base.rstrip("/")


def telegram_method_url(token: str, method: str) -> str:
    """Build ``{base}/bot{token}/{method}``."""
    return f"{telegram_api_base()}/bot{token}/{method}"


def _telegram_proxy_url() -> str:
    """Optional HTTPS proxy for Telegram egress (``TELEGRAM_PROXY_URL`` / env)."""
    explicit = (getattr(settings, "TELEGRAM_PROXY_URL", "") or "").strip()
    if explicit:
        return explicit
    return (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()


def _telegram_urlopen(
    request: Request,
    *,
    timeout: float = _TELEGRAM_TIMEOUT_SEC,
) -> HTTPResponse:
    """urlopen with optional proxy and short retries (network / 5xx / 429)."""
    if not request.has_header("User-agent"):
        request.add_header("User-Agent", _TELEGRAM_USER_AGENT)
    proxy = _telegram_proxy_url()
    last_exc: BaseException | None = None
    for attempt in range(_TELEGRAM_RETRIES):
        try:
            if proxy:
                opener = build_opener(ProxyHandler({"https": proxy, "http": proxy}))
                return opener.open(request, timeout=timeout)  # noqa: S310
            return urlopen(request, timeout=timeout)  # noqa: S310
        except HTTPError as exc:
            last_exc = exc
            if exc.code < 500 and exc.code != 429:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            last_exc = exc
        if attempt + 1 < _TELEGRAM_RETRIES:
            time.sleep(0.15 * (2**attempt))
    assert last_exc is not None
    raise last_exc


def _post_json(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    open_fn: UrlOpenFn = urlopen,
    timeout: float = _HTTP_TIMEOUT_SEC,
) -> tuple[int, dict[str, Any]]:
    """POST JSON and return status + parsed body (empty dict on non-JSON)."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request = Request(url, data=body, headers=req_headers, method="POST")
    with open_fn(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read().decode("utf-8", errors="replace")
        status = getattr(response, "status", 200)
    return int(status), _parse_json_dict(raw)


def _parse_json_dict(raw: str) -> dict[str, Any]:
    """Parse JSON object; wrap non-objects."""
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw[:500]}
    if not isinstance(data, dict):
        return {"raw": data}
    return data


def _post_multipart(
    url: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    open_fn: UrlOpenFn = urlopen,
    timeout: float = _HTTP_TIMEOUT_SEC,
) -> tuple[int, dict[str, Any]]:
    """POST multipart/form-data (Telegram file upload).

    Args:
        url: Endpoint URL.
        fields: Text form fields.
        files: ``name -> (filename, content, content_type)``.
        open_fn: urllib opener (Telegram uses retries + optional proxy).
        timeout: Socket timeout seconds.
    """
    boundary = f"----HooconBoundary{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, content, content_type) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        disposition = f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        chunks.append(disposition.encode())
        chunks.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    with open_fn(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read().decode("utf-8", errors="replace")
        status = getattr(response, "status", 200)
    return int(status), _parse_json_dict(raw)


def _telegram_api_result(status: int, data: dict[str, Any]) -> PublishResult:
    """Map Telegram Bot API JSON to PublishResult."""
    if status >= 400 or not data.get("ok"):
        desc = str(data.get("description") or data.get("raw") or status)[:300]
        return PublishResult(ok=False, error=f"Telegram: {desc}")
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    mid = result.get("message_id", "") if isinstance(result, dict) else ""
    return PublishResult(ok=True, external_id=str(mid))


def telegram_api_call(method: str, payload: dict[str, Any] | None = None) -> PublishResult:
    """POST JSON to ``{TELEGRAM_API_BASE}/bot<token>/<method>``."""
    token = telegram_bot_token()
    if not token:
        return PublishResult(ok=False, skipped=True, error="Telegram не настроен")
    url = telegram_method_url(token, method)
    try:
        status, data = _post_json(
            url,
            payload=payload or {},
            open_fn=_telegram_urlopen,
            timeout=_TELEGRAM_TIMEOUT_SEC,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("telegram_api_%s_failed error=%s", method, type(exc).__name__)
        return PublishResult(ok=False, error=f"Telegram: {type(exc).__name__}")
    return _telegram_api_result(status, data)


def publish_telegram(
    *,
    chat_id: str,
    text: str,
    photo_path: Path | str | None = None,
    photo_url: str | None = None,
    reply_markup: dict[str, Any] | None = None,
) -> PublishResult:
    """Send message (or cover photo + caption) via Telegram Bot API.

    Prefer public ``photo_url`` (Telegram fetches it; smaller egress from VPS);
    else local ``photo_path`` (multipart ``sendPhoto``); else plain
    ``sendMessage``. Caption / text uses HTML parse_mode (Telegram HTML subset).

    Args:
        chat_id: Target chat / channel id.
        text: Message body or photo caption (HTML).
        photo_path: Local cover file path when available.
        photo_url: Absolute HTTPS URL Telegram can fetch.
        reply_markup: Optional ReplyKeyboard / InlineKeyboard markup dict.

    Returns:
        PublishResult with Telegram message_id when successful.
    """
    token = telegram_bot_token()
    if not token or not chat_id.strip():
        return PublishResult(ok=False, skipped=True, error="Telegram не настроен")

    chat = chat_id.strip()
    if photo_url and photo_url.strip():
        return _publish_telegram_photo_url(
            token,
            chat=chat,
            caption=text,
            photo_url=photo_url.strip(),
            reply_markup=reply_markup,
        )
    path = Path(photo_path) if photo_path else None
    if path is not None and path.is_file():
        return _publish_telegram_photo_file(
            token,
            chat=chat,
            caption=text,
            path=path,
            reply_markup=reply_markup,
        )
    return _publish_telegram_message(
        token,
        chat=chat,
        text=text,
        reply_markup=reply_markup,
    )


def _attach_reply_markup(
    payload: dict[str, Any],
    reply_markup: dict[str, Any] | None,
) -> dict[str, Any]:
    """Copy payload and add reply_markup when provided."""
    if reply_markup is None:
        return payload
    out = dict(payload)
    out["reply_markup"] = reply_markup
    return out


def _publish_telegram_message(
    token: str,
    *,
    chat: str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> PublishResult:
    """Plain sendMessage with HTML parse_mode."""
    url = telegram_method_url(token, "sendMessage")
    try:
        status, data = _post_json(
            url,
            payload=_attach_reply_markup(
                {
                    "chat_id": chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                },
                reply_markup,
            ),
            open_fn=_telegram_urlopen,
            timeout=_TELEGRAM_TIMEOUT_SEC,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("telegram_publish_failed error=%s", type(exc).__name__)
        return PublishResult(ok=False, error=f"Telegram: {type(exc).__name__}")
    return _telegram_api_result(status, data)


def _publish_telegram_photo_url(
    token: str,
    *,
    chat: str,
    caption: str,
    photo_url: str,
    reply_markup: dict[str, Any] | None = None,
) -> PublishResult:
    """sendPhoto with a publicly reachable photo URL."""
    url = telegram_method_url(token, "sendPhoto")
    try:
        status, data = _post_json(
            url,
            payload=_attach_reply_markup(
                {
                    "chat_id": chat,
                    "photo": photo_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
                reply_markup,
            ),
            open_fn=_telegram_urlopen,
            timeout=_TELEGRAM_TIMEOUT_SEC,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("telegram_photo_url_failed error=%s", type(exc).__name__)
        return PublishResult(ok=False, error=f"Telegram: {type(exc).__name__}")
    return _telegram_api_result(status, data)


def _publish_telegram_photo_file(
    token: str,
    *,
    chat: str,
    caption: str,
    path: Path,
    reply_markup: dict[str, Any] | None = None,
) -> PublishResult:
    """sendPhoto multipart upload from a local cover file."""
    url = telegram_method_url(token, "sendPhoto")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    fields = {
        "chat_id": chat,
        "caption": caption,
        "parse_mode": "HTML",
    }
    if reply_markup is not None:
        fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
    try:
        content = path.read_bytes()
        status, data = _post_multipart(
            url,
            fields=fields,
            files={"photo": (path.name, content, content_type)},
            open_fn=_telegram_urlopen,
            timeout=_TELEGRAM_TIMEOUT_SEC,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("telegram_photo_file_failed error=%s", type(exc).__name__)
        return PublishResult(ok=False, error=f"Telegram: {type(exc).__name__}")
    return _telegram_api_result(status, data)


def publish_vk(*, group_id: str, text: str) -> PublishResult:
    """Post to VK community wall (wall.post).

    Args:
        group_id: Numeric group id without minus (owner_id = -group_id).
        text: Wall message.

    Returns:
        PublishResult with VK post_id when successful.
    """
    token = vk_access_token()
    gid = group_id.strip().lstrip("-")
    if not token or not gid.isdigit():
        return PublishResult(ok=False, skipped=True, error="VK не настроен")
    owner_id = f"-{gid}"
    query = urlencode(
        {
            "access_token": token,
            "v": "5.199",
            "owner_id": owner_id,
            "from_group": "1",
            "message": text,
        }
    )
    url = f"https://api.vk.com/method/wall.post?{query}"
    request = Request(url, method="POST", data=b"")
    try:
        with urlopen(request, timeout=_HTTP_TIMEOUT_SEC) as response:  # noqa: S310
            raw = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("vk_publish_failed error=%s", type(exc).__name__)
        return PublishResult(ok=False, error=f"VK: {type(exc).__name__}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return PublishResult(ok=False, error="VK: invalid JSON")
    if "error" in data:
        err = data["error"]
        msg = err.get("error_msg", str(err)) if isinstance(err, dict) else str(err)
        return PublishResult(ok=False, error=f"VK: {msg}"[:300])
    resp = data.get("response") if isinstance(data.get("response"), dict) else {}
    post_id = resp.get("post_id", "")
    return PublishResult(ok=True, external_id=str(post_id))


def publish_max(*, chat_id: str, text: str) -> PublishResult:
    """Send message via MAX Bot API (platform-api2.max.ru).

    Args:
        chat_id: Chat id for the bot.
        text: Message body.

    Returns:
        PublishResult when successful.
    """
    token = max_bot_token()
    if not token or not chat_id.strip():
        return PublishResult(ok=False, skipped=True, error="MAX не настроен")
    url = f"https://platform-api2.max.ru/messages?chat_id={chat_id.strip()}"
    try:
        status, data = _post_json(
            url,
            payload={"text": text},
            headers={"Authorization": token},
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.warning("max_publish_failed error=%s", type(exc).__name__)
        return PublishResult(ok=False, error=f"MAX: {type(exc).__name__}")

    if status >= 400:
        return PublishResult(ok=False, error=f"MAX HTTP {status}")
    # Response shape varies; keep message id if present.
    mid = ""
    if isinstance(data.get("message"), dict):
        mid = str(data["message"].get("body", {}).get("mid") or data["message"].get("id") or "")
    if not mid:
        mid = str(data.get("message_id") or data.get("id") or "")
    return PublishResult(ok=True, external_id=mid)
