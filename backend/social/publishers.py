"""HTTP publishers for Telegram, VK and MAX (stdlib urllib)."""

from __future__ import annotations

import json
import logging
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sitesettings.credentials import max_bot_token, telegram_bot_token, vk_access_token

logger = logging.getLogger("hoocon.social")

_HTTP_TIMEOUT_SEC = 20


@dataclass(frozen=True)
class PublishResult:
    """Outcome of one channel publish call."""

    ok: bool
    external_id: str = ""
    error: str = ""
    skipped: bool = False


def _post_json(
    url: str,
    *,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """POST JSON and return status + parsed body (empty dict on non-JSON)."""
    body = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request = Request(url, data=body, headers=req_headers, method="POST")
    with urlopen(request, timeout=_HTTP_TIMEOUT_SEC) as response:  # noqa: S310
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
) -> tuple[int, dict[str, Any]]:
    """POST multipart/form-data (Telegram file upload).

    Args:
        url: Endpoint URL.
        fields: Text form fields.
        files: ``name -> (filename, content, content_type)``.
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
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\n'
            ).encode()
        )
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
    with urlopen(request, timeout=_HTTP_TIMEOUT_SEC) as response:  # noqa: S310
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


def publish_telegram(
    *,
    chat_id: str,
    text: str,
    photo_path: Path | str | None = None,
    photo_url: str | None = None,
) -> PublishResult:
    """Send message (or cover photo + caption) via Telegram Bot API.

    Prefer local ``photo_path`` (multipart ``sendPhoto``); else public
    ``photo_url``; else plain ``sendMessage``. Caption / text uses HTML
    parse_mode (Telegram HTML subset).

    Args:
        chat_id: Target chat / channel id.
        text: Message body or photo caption (HTML).
        photo_path: Local cover file path when available.
        photo_url: Absolute HTTPS URL Telegram can fetch.

    Returns:
        PublishResult with Telegram message_id when successful.
    """
    token = telegram_bot_token()
    if not token or not chat_id.strip():
        return PublishResult(ok=False, skipped=True, error="Telegram не настроен")

    chat = chat_id.strip()
    path = Path(photo_path) if photo_path else None
    if path is not None and path.is_file():
        return _publish_telegram_photo_file(token, chat=chat, caption=text, path=path)
    if photo_url and photo_url.strip():
        return _publish_telegram_photo_url(token, chat=chat, caption=text, photo_url=photo_url.strip())
    return _publish_telegram_message(token, chat=chat, text=text)


def _publish_telegram_message(token: str, *, chat: str, text: str) -> PublishResult:
    """Plain sendMessage with HTML parse_mode."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        status, data = _post_json(
            url,
            payload={
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
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
) -> PublishResult:
    """sendPhoto with a publicly reachable photo URL."""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        status, data = _post_json(
            url,
            payload={
                "chat_id": chat,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            },
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
) -> PublishResult:
    """sendPhoto multipart upload from a local cover file."""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        content = path.read_bytes()
        status, data = _post_multipart(
            url,
            fields={
                "chat_id": chat,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={"photo": (path.name, content, content_type)},
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
