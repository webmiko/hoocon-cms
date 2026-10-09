"""FCM HTTP v1 push to the manager app (service-account OAuth, toggles)."""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

from staff_api.fcm import SendResult, ServiceAccount, send_fcm_message, signed_assertion

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_ACCOUNT_JSON = json.dumps(
    {
        "project_id": "hoocon-manager",
        "client_email": "push@hoocon-manager.iam.gserviceaccount.com",
        "private_key": _PEM,
        "token_uri": "https://oauth2.googleapis.com/token",
    },
)


class _Resp:
    def __init__(self, status: int = 200, payload: dict | None = None) -> None:
        self.status = status
        self._body = json.dumps(payload or {}).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


def test_legacy_fcm_endpoint_is_gone() -> None:
    """Legacy /fcm/send с server key выключен Google в 2024 — push не доходили."""
    backend = Path(__file__).resolve().parents[1]
    for rel in ("staff_api/tasks.py", "staff_api/fcm.py", "config/settings.py"):
        text = (backend / rel).read_text(encoding="utf-8")
        assert "fcm.googleapis.com/fcm/send" not in text
        assert "FCM_SERVER_KEY" not in text


def test_signed_assertion_is_valid_rs256_for_firebase_scope() -> None:
    account = ServiceAccount("p", "svc@p.iam.gserviceaccount.com", _PEM)
    jwt = signed_assertion(account, now=1_000)
    header, claims, signature = jwt.split(".")
    assert json.loads(_b64decode(header)) == {"alg": "RS256", "typ": "JWT"}
    payload = json.loads(_b64decode(claims))
    assert payload["iss"] == "svc@p.iam.gserviceaccount.com"
    assert payload["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
    assert payload["aud"] == "https://oauth2.googleapis.com/token"
    assert payload["exp"] - payload["iat"] == 3600
    _KEY.public_key().verify(_b64decode(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())


@override_settings(FCM_SERVICE_ACCOUNT_JSON=_ACCOUNT_JSON, FCM_SERVICE_ACCOUNT_FILE="")
def test_send_uses_v1_endpoint_with_cached_bearer_token() -> None:
    requests: list = []

    def fake_urlopen(req, timeout: int):
        requests.append(req)
        if req.full_url.endswith("/token"):
            return _Resp(payload={"access_token": "ya29.token", "expires_in": 3600})
        return _Resp()

    with patch("staff_api.fcm.urllib.request.urlopen", side_effect=fake_urlopen):
        for _ in range(2):
            result = send_fcm_message(token="dev-1", title="T", body="B", data={"type": "lead"})
            assert result is SendResult.SENT

    token_calls = [r for r in requests if r.full_url.endswith("/token")]
    send_calls = [r for r in requests if "messages:send" in r.full_url]
    assert len(token_calls) == 1
    assert len(send_calls) == 2
    send = send_calls[0]
    assert send.full_url == "https://fcm.googleapis.com/v1/projects/hoocon-manager/messages:send"
    assert send.get_header("Authorization") == "Bearer ya29.token"
    message = json.loads(send.data)["message"]
    assert message["token"] == "dev-1"
    assert message["notification"] == {"title": "T", "body": "B"}
    assert message["data"] == {"type": "lead"}


@override_settings(FCM_SERVICE_ACCOUNT_JSON="", FCM_SERVICE_ACCOUNT_FILE="")
def test_send_without_service_account_is_noop() -> None:
    with patch("staff_api.fcm.urllib.request.urlopen") as urlopen:
        assert send_fcm_message(token="t", title="T", body="B", data={}) is SendResult.FAILED
    urlopen.assert_not_called()


def _staff_device(token: str):
    from staff_api.models import StaffDevice

    user = get_user_model().objects.create_user(username=f"u-{token}", password="x", is_staff=True)
    return StaffDevice.objects.create(user=user, fcm_token=token, platform="android")


@pytest.mark.django_db
@override_settings(FCM_SERVICE_ACCOUNT_JSON=_ACCOUNT_JSON, FCM_SERVICE_ACCOUNT_FILE="")
def test_unregistered_device_token_is_forgotten() -> None:
    from leads.models import Lead
    from staff_api.models import StaffDevice
    from staff_api.tasks import notify_staff_fcm_new_lead

    _staff_device("stale-token")
    lead = Lead.objects.create(name="Иван", email="i@example.com", message="x" * 20)

    def fake_urlopen(req, timeout: int):
        if req.full_url.endswith("/token"):
            return _Resp(payload={"access_token": "ya29.token", "expires_in": 3600})
        raise HTTPError(req.full_url, 404, "NOT_FOUND", {}, BytesIO(b"{}"))

    with patch("staff_api.fcm.urllib.request.urlopen", side_effect=fake_urlopen):
        assert notify_staff_fcm_new_lead(lead.pk) == 0
    assert not StaffDevice.objects.filter(fcm_token="stale-token").exists()


@pytest.mark.django_db
def test_fcm_tasks_respect_site_settings_toggles() -> None:
    """FCM слал push даже при выключенных тумблерах уведомлений в настройках сайта."""
    from leads.models import Lead
    from sitesettings.models import SiteSettings
    from staff_api.tasks import notify_staff_fcm_new_lead, notify_staff_fcm_support
    from supportchat.models import Channel, Conversation

    _staff_device("on-device")
    site = SiteSettings.load()
    site.staff_push_leads_enabled = False
    site.staff_push_support_enabled = False
    site.save()
    lead = Lead.objects.create(name="Иван", email="i2@example.com", message="x" * 20)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="fcm-toggle")

    with patch("staff_api.tasks._send_fcm", return_value=True) as send:
        assert notify_staff_fcm_new_lead(lead.pk) == 0
        assert notify_staff_fcm_support(conv.pk) == 0
    send.assert_not_called()
