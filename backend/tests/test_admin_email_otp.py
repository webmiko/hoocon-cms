"""Tests for passwordless Admin Email OTP."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings

from config.admin_otp import hash_otp_code, mask_email, normalize_otp_input

User = get_user_model()

OTP_SETTINGS = {
    "ADMIN_EMAIL_OTP_ENABLED": True,
    "ADMIN_EMAIL_OTP_TTL_SECONDS": 600,
    "ADMIN_EMAIL_OTP_MAX_ATTEMPTS": 5,
    "ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS": 60,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "AXES_ENABLED": False,
}


def _csrf_post(client: Client, url: str, data: dict[str, str]) -> object:
    client.get("/admin/login/")
    csrf = client.cookies["csrftoken"].value
    return client.post(url, {**data, "csrfmiddlewaretoken": csrf})


def _staff(*, username: str, email: str) -> object:
    return User.objects.create_superuser(
        username=username,
        email=email,
        password="UnusedPass123!",
    )


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_admin_login_sends_otp_and_does_not_authenticate() -> None:
    admin_user = _staff(username="otp-admin", email="otp-admin@example.com")
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/",
        {"username": admin_user.username, "next": "/admin/"},
    )
    assert response.status_code == 302
    assert response["Location"].endswith("/admin/otp/")
    assert len(mail.outbox) == 1
    assert "код" in mail.outbox[0].subject.lower()
    assert client.session.get("_auth_user_id") is None
    assert client.session.get("admin_otp_user_id") == admin_user.pk


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_admin_otp_happy_path_logs_in() -> None:
    admin_user = _staff(username="otp-ok", email="otp-ok@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="424242"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.email, "next": "/admin/"},
        )
    otp_page = client.get("/admin/otp/")
    assert otp_page.status_code == 200
    assert b"424242" not in otp_page.content
    assert mask_email(admin_user.email).encode() in otp_page.content

    csrf = client.cookies["csrftoken"].value
    done = client.post(
        "/admin/otp/",
        {"otp_code": "424242", "csrfmiddlewaretoken": csrf},
    )
    assert done.status_code == 302
    assert done["Location"].endswith("/admin/")
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert client.session.get("admin_otp_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_admin_otp_wrong_code_stays_anonymous() -> None:
    admin_user = _staff(username="otp-bad", email="otp-bad@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="111111"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    csrf = client.cookies["csrftoken"].value
    bad = client.post(
        "/admin/otp/",
        {"otp_code": "000000", "csrfmiddlewaretoken": csrf},
    )
    assert bad.status_code == 200
    assert client.session.get("_auth_user_id") is None
    assert client.session.get("admin_otp_user_id") == admin_user.pk


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_admin_otp_resend_cooldown() -> None:
    admin_user = _staff(username="otp-resend", email="otp-resend@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="222222"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    assert len(mail.outbox) == 1
    csrf = client.cookies["csrftoken"].value
    again = client.post(
        "/admin/otp/resend/",
        {"csrfmiddlewaretoken": csrf},
    )
    assert again.status_code == 302
    # Still one mail — cooldown blocked second send.
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False, AXES_ENABLED=False)
def test_admin_password_login_when_otp_disabled() -> None:
    admin_user = _staff(username="pwd-admin", email="pwd-admin@example.com")
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/",
        {
            "username": admin_user.username,
            "password": "UnusedPass123!",
            "next": "/admin/",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith("/admin/")
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_unknown_login_does_not_send_mail() -> None:
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/",
        {"username": "nobody@example.com", "next": "/admin/"},
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 0
    assert client.session.get("_auth_user_id") is None


def test_normalize_and_mask_helpers() -> None:
    assert normalize_otp_input("12 34-56") == "123456"
    assert mask_email("ab@hoocon.ru") == "a***@hoocon.ru"
    assert len(hash_otp_code("123456")) == 64


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()
