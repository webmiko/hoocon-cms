"""GigaChat HTTP client: OAuth token cache + chat completions (stdlib only)."""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from django.conf import settings

logger = logging.getLogger("hoocon.supportchat.gigachat")

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_BASE = "https://api.giga.chat/v1"

_TOKEN_CACHE: dict[str, Any] = {"access_token": "", "expires_at_ms": 0}


class GigachatError(Exception):
    """GigaChat API or configuration error."""


def is_configured() -> bool:
    """Return True when credentials are set (Admin or env)."""
    from sitesettings.credentials import gigachat_credentials

    return bool(gigachat_credentials())


def _ssl_context() -> ssl.SSLContext | None:
    verify = getattr(settings, "GIGACHAT_VERIFY_SSL", True)
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _post_json(
    url: str,
    *,
    headers: dict[str, str],
    body: bytes | None = None,
) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, context=_ssl_context(), timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GigachatError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GigachatError(f"Сеть: {exc.reason}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GigachatError(f"Некорректный JSON: {raw[:200]}") from exc
    if not isinstance(data, dict):
        raise GigachatError("Ожидался JSON-объект в ответе API")
    return data


def fetch_access_token() -> str:
    """Obtain Bearer token (cached until ~1 min before expiry)."""
    now_ms = int(time.time() * 1000)
    cached = (_TOKEN_CACHE.get("access_token") or "").strip()
    expires_at = int(_TOKEN_CACHE.get("expires_at_ms") or 0)
    if cached and expires_at > now_ms + 60_000:
        return cached

    from sitesettings.credentials import gigachat_credentials

    credentials = gigachat_credentials()
    if not credentials:
        raise GigachatError("GIGACHAT_CREDENTIALS не задан")

    scope = getattr(settings, "GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
    body = f"scope={scope}".encode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {credentials}",
    }
    data = _post_json(OAUTH_URL, headers=headers, body=body)
    token = (data.get("access_token") or "").strip()
    if not token:
        raise GigachatError(f"Нет access_token в ответе OAuth: {data}")
    expires_at_ms = int(data.get("expires_at") or 0)
    _TOKEN_CACHE["access_token"] = token
    _TOKEN_CACHE["expires_at_ms"] = expires_at_ms or (now_ms + 30 * 60 * 1000)
    logger.debug("gigachat_token_refreshed expires_at_ms=%s", expires_at_ms)
    return token


def chat_completion(messages: list[dict[str, str]], *, model: str | None = None) -> str:
    """Call POST /chat/completions and return assistant text."""
    token = fetch_access_token()
    raw_model = model or getattr(settings, "GIGACHAT_MODEL", "GigaChat")
    model_name = str(raw_model).strip()
    payload = json.dumps(
        {
            "model": model_name,
            "messages": messages,
            "stream": False,
            "temperature": 0,
        },
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    data = _post_json(f"{API_BASE}/chat/completions", headers=headers, body=payload)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GigachatError(f"Пустой choices в ответе: {data}")
    first = choices[0]
    if not isinstance(first, dict):
        raise GigachatError("Некорректный формат choices[0]")
    message = first.get("message")
    if not isinstance(message, dict):
        raise GigachatError("Нет message в choices[0]")
    content = (message.get("content") or "").strip()
    if not content:
        raise GigachatError("Пустой content в ответе модели")
    return content
