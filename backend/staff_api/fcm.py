"""Firebase Cloud Messaging HTTP v1 for the manager app.

The legacy ``/fcm/send`` + server-key API was shut down by Google in 2024.
v1 needs an OAuth2 access token minted from a service-account key
(``FCM_SERVICE_ACCOUNT_FILE`` or ``FCM_SERVICE_ACCOUNT_JSON``).
"""

from __future__ import annotations

import base64
import enum
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SEND_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
_TOKEN_CACHE_KEY = "fcm:v1:access_token"
_TOKEN_LIFETIME = 3600
_TIMEOUT = 10


class SendResult(enum.Enum):
    SENT = "sent"
    INVALID_TOKEN = "invalid_token"
    FAILED = "failed"


@dataclass(frozen=True)
class ServiceAccount:
    project_id: str
    client_email: str
    private_key: str
    token_uri: str = _DEFAULT_TOKEN_URI


def load_service_account() -> ServiceAccount | None:
    """Service account from settings; None when FCM is not configured."""
    raw = str(getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "") or "").strip()
    path = str(getattr(settings, "FCM_SERVICE_ACCOUNT_FILE", "") or "").strip()
    if not raw and path:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            logger.warning("fcm_service_account_unreadable path=%s", path)
            return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return ServiceAccount(
            project_id=data["project_id"],
            client_email=data["client_email"],
            private_key=data["private_key"],
            token_uri=data.get("token_uri") or _DEFAULT_TOKEN_URI,
        )
    except (ValueError, KeyError, TypeError):
        logger.warning("fcm_service_account_invalid")
        return None


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def signed_assertion(account: ServiceAccount, *, now: int | None = None) -> str:
    """RS256 JWT for the OAuth2 jwt-bearer grant."""
    issued = int(time.time()) if now is None else now
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": account.client_email,
        "scope": _SCOPE,
        "aud": account.token_uri,
        "iat": issued,
        "exp": issued + _TOKEN_LIFETIME,
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode("utf-8")) for part in (header, claims)
    )
    key = serialization.load_pem_private_key(account.private_key.encode("utf-8"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("FCM service account key must be RSA")
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def access_token(account: ServiceAccount) -> str | None:
    """Cached OAuth2 access token (refreshed a few minutes before expiry)."""
    cached = cache.get(_TOKEN_CACHE_KEY)
    if cached:
        return str(cached)
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_assertion(account),
        },
    ).encode("ascii")
    req = urllib.request.Request(  # noqa: S310 — token_uri from the service account
        account.token_uri,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        logger.warning("fcm_token_failed error=%s", type(exc).__name__)
        return None
    token = str(payload.get("access_token") or "")
    if not token:
        return None
    ttl = max(60, int(payload.get("expires_in") or _TOKEN_LIFETIME) - 300)
    cache.set(_TOKEN_CACHE_KEY, token, timeout=ttl)
    return token


def send_fcm_message(*, token: str, title: str, body: str, data: dict[str, str]) -> SendResult:
    """Send one notification; INVALID_TOKEN means the device should be forgotten."""
    account = load_service_account()
    if account is None:
        logger.debug("FCM service account unset — skip push")
        return SendResult.FAILED
    bearer = access_token(account)
    if not bearer:
        return SendResult.FAILED
    message = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": data,
            "android": {"priority": "HIGH"},
            "apns": {"headers": {"apns-priority": "10"}},
        },
    }
    req = urllib.request.Request(  # noqa: S310 — fixed FCM host
        _SEND_URL.format(project=urllib.parse.quote(account.project_id, safe="")),
        data=json.dumps(message).encode("utf-8"),
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            return SendResult.SENT if 200 <= resp.status < 300 else SendResult.FAILED
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            cache.delete(_TOKEN_CACHE_KEY)
        if exc.code == 404:
            return SendResult.INVALID_TOKEN
        logger.warning("fcm_http_error status=%s", exc.code)
        return SendResult.FAILED
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("fcm_send_failed error=%s", type(exc).__name__)
        return SendResult.FAILED
