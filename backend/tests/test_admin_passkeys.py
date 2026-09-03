"""Tests for Admin WebAuthn passkey login / register / delete."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import PasskeyCredential

User = get_user_model()

PASSKEY_SETTINGS = {
    "ADMIN_PASSKEY_ENABLED": True,
    "ADMIN_PASSKEY_RP_ID": "localhost",
    "ADMIN_PASSKEY_RP_NAME": "HOOCON CMS Test",
    "ADMIN_PASSKEY_ORIGIN": "http://localhost:8000",
    "ADMIN_PASSKEY_CHALLENGE_TTL_SECONDS": 300,
    "ADMIN_EMAIL_OTP_ENABLED": False,
    "AXES_ENABLED": False,
}


def _csrf_json(client: Client, url: str, payload: dict) -> object:
    client.get("/admin/login/")
    csrf = client.cookies["csrftoken"].value
    return client.post(
        url,
        data=__import__("json").dumps(payload),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _staff(*, username: str = "pk-admin", email: str = "pk-admin@example.com") -> object:
    return User.objects.create_superuser(
        username=username,
        email=email,
        password="password12",
    )


@pytest.mark.django_db
@override_settings(ADMIN_PASSKEY_ENABLED=False)
def test_passkey_endpoints_404_when_disabled() -> None:
    client = Client()
    for name in (
        "admin:passkey_login_begin",
        "admin:passkey_login_complete",
        "admin:passkey_register_begin",
        "admin:passkey_register_complete",
        "admin:passkey_manage",
    ):
        url = reverse(name)
        response = client.post(url) if "manage" not in name else client.get(url)
        assert response.status_code == 404, name


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_login_page_shows_passkey_button() -> None:
    client = Client()
    response = client.get("/admin/login/")
    assert response.status_code == 200
    assert b"data-passkey-login" in response.content
    assert "Войти с ключом доступа".encode() in response.content
    assert b"hoocon-admin-passkeys.js" in response.content


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_login_begin_stores_challenge() -> None:
    client = Client()
    response = _csrf_json(client, reverse("admin:passkey_login_begin"), {"next": "/admin/"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "challenge" in data["publicKey"]
    assert client.session.get("admin_passkey_auth_challenge")


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_register_begin_requires_staff() -> None:
    client = Client()
    response = _csrf_json(client, reverse("admin:passkey_register_begin"), {})
    assert response.status_code in (302, 401, 403)


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_register_begin_for_staff() -> None:
    user = _staff()
    client = Client()
    client.force_login(user)
    client.get("/admin/")
    csrf = client.cookies["csrftoken"].value
    response = client.post(
        reverse("admin:passkey_register_begin"),
        data="{}",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["publicKey"]["rp"]["id"] == "localhost"
    assert client.session.get("admin_passkey_reg_challenge")
    assert client.session.get("admin_passkey_reg_user_id") == user.pk


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_register_complete_persists_credential() -> None:
    user = _staff(username="pk-reg", email="pk-reg@example.com")
    client = Client()
    client.force_login(user)
    client.get("/admin/")
    csrf = client.cookies["csrftoken"].value
    client.post(
        reverse("admin:passkey_register_begin"),
        data="{}",
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )

    verified = MagicMock()
    verified.credential_id = b"\x01\x02\x03\x04cred-id-bytes"
    verified.credential_public_key = b"\x05\x06public-key"
    verified.sign_count = 0

    with patch(
        "accounts.passkeys.verify_registration_response",
        return_value=verified,
    ):
        response = client.post(
            reverse("admin:passkey_register_complete"),
            data=__import__("json").dumps(
                {
                    "credential": {"id": "fake", "type": "public-key", "response": {}},
                    "device_name": "MacBook Test",
                },
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["ok"] is True
    assert data["device_name"] == "MacBook Test"
    assert PasskeyCredential.objects.filter(user=user).count() == 1
    row = PasskeyCredential.objects.get(user=user)
    assert row.device_name == "MacBook Test"
    assert bytes(row.public_key) == b"\x05\x06public-key"


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_login_complete_logs_in_staff() -> None:
    user = _staff(username="pk-login", email="pk-login@example.com")
    from webauthn.helpers import bytes_to_base64url

    cred_bytes = b"\xaa\xbb\xcc\xddlogin-cred"
    PasskeyCredential.objects.create(
        user=user,
        credential_id=bytes_to_base64url(cred_bytes),
        public_key=b"\x11\x22pub",
        sign_count=1,
        device_name="Phone",
    )

    client = Client()
    _csrf_json(client, reverse("admin:passkey_login_begin"), {"next": "/admin/"})
    csrf = client.cookies["csrftoken"].value

    verified = MagicMock()
    verified.new_sign_count = 2

    with patch(
        "accounts.passkeys.verify_authentication_response",
        return_value=verified,
    ):
        response = client.post(
            reverse("admin:passkey_login_complete"),
            data=__import__("json").dumps(
                {
                    "credential": {
                        "id": bytes_to_base64url(cred_bytes),
                        "rawId": bytes_to_base64url(cred_bytes),
                        "type": "public-key",
                        "response": {},
                    },
                },
            ),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["ok"] is True
    assert data["redirect"] == "/admin/"
    assert client.session.get("_auth_user_id") == str(user.pk)
    row = PasskeyCredential.objects.get(user=user)
    assert row.sign_count == 2
    assert row.last_used_at is not None


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_login_complete_rejects_non_staff() -> None:
    user = User.objects.create_user(
        username="pk-plain",
        email="pk-plain@example.com",
        password="password12",
        is_staff=False,
        is_active=True,
    )
    from webauthn.helpers import bytes_to_base64url

    cred_bytes = b"\x01nonstaff"
    PasskeyCredential.objects.create(
        user=user,
        credential_id=bytes_to_base64url(cred_bytes),
        public_key=b"\x00",
        sign_count=0,
    )
    client = Client()
    _csrf_json(client, reverse("admin:passkey_login_begin"), {})
    csrf = client.cookies["csrftoken"].value
    response = client.post(
        reverse("admin:passkey_login_complete"),
        data=__import__("json").dumps(
            {
                "credential": {
                    "id": bytes_to_base64url(cred_bytes),
                    "type": "public-key",
                    "response": {},
                },
            },
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_delete_own_passkey() -> None:
    user = _staff(username="pk-del", email="pk-del@example.com")
    row = PasskeyCredential.objects.create(
        user=user,
        credential_id="abc123delete",
        public_key=b"\x01",
        sign_count=0,
        device_name="ToDelete",
    )
    client = Client()
    client.force_login(user)
    response = client.post(reverse("admin:passkey_delete", args=[row.pk]))
    assert response.status_code == 302
    assert not PasskeyCredential.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_delete_other_passkey_forbidden_for_non_superuser() -> None:
    owner = _staff(username="pk-owner", email="pk-owner@example.com")
    other = User.objects.create_user(
        username="pk-mgr",
        email="pk-mgr@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    row = PasskeyCredential.objects.create(
        user=owner,
        credential_id="other-key",
        public_key=b"\x02",
        sign_count=0,
    )
    client = Client()
    client.force_login(other)
    response = client.post(
        reverse("admin:passkey_delete", args=[row.pk]),
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 403
    assert PasskeyCredential.objects.filter(pk=row.pk).exists()


@pytest.mark.django_db
@override_settings(**PASSKEY_SETTINGS)
def test_manage_page_ok_for_staff() -> None:
    user = _staff(username="pk-mgmt", email="pk-mgmt@example.com")
    client = Client()
    client.force_login(user)
    response = client.get(reverse("admin:passkey_manage"))
    assert response.status_code == 200
    assert "Ключи доступа".encode() in response.content
    assert b"data-passkey-register" in response.content
