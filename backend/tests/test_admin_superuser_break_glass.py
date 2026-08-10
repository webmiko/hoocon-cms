"""Tests for superuser Admin break-glass (password + recovery codes)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from accounts.models import SuperuserRecoveryCode
from accounts.recovery_codes import (
    consume_recovery_code,
    hash_recovery_code,
    normalize_recovery_code,
    replace_recovery_codes,
    unused_recovery_code_count,
)

User = get_user_model()

OTP_SETTINGS = {
    "ADMIN_EMAIL_OTP_ENABLED": True,
    "ADMIN_EMAIL_OTP_TTL_SECONDS": 300,
    "ADMIN_EMAIL_OTP_MAX_ATTEMPTS": 5,
    "ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS": 60,
    "ADMIN_EMAIL_OTP_ALLOWED_EMAILS": "",
    "ADMIN_EMAIL_OTP_REQUEST_LIMIT": 50,
    "ADMIN_EMAIL_OTP_REQUEST_WINDOW_SECONDS": 600,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    "AXES_ENABLED": False,
}


def _csrf_post(client: Client, url: str, data: dict[str, str]) -> object:
    client.get(url.split("?")[0] if "?" in url else url)
    # Password/recovery modes need the mode page for CSRF cookie.
    if "mode=" in url:
        client.get(url)
    else:
        client.get("/admin/login/")
    csrf = client.cookies["csrftoken"].value
    return client.post(url, {**data, "csrfmiddlewaretoken": csrf})


def _superuser(*, username: str, email: str, password: str = "password12") -> object:
    return User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )


def _staff_non_super(*, username: str, email: str, password: str = "password12") -> object:
    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=True,
        is_active=True,
        is_superuser=False,
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_superuser_password_login_when_otp_enabled() -> None:
    admin_user = _superuser(username="su-pwd", email="su-pwd@example.com")
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/?mode=password",
        {
            "mode": "password",
            "username": admin_user.email,
            "password": "password12",
            "next": "/admin/",
        },
    )
    assert response.status_code == 302
    assert "/admin/" in response["Location"]
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_non_superuser_password_rejected_when_otp_enabled() -> None:
    staff = _staff_non_super(username="mgr-pwd", email="mgr-pwd@example.com")
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/?mode=password",
        {
            "mode": "password",
            "username": staff.username,
            "password": "password12",
            "next": "/admin/",
        },
    )
    assert response.status_code == 200
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_recovery_login_ok_and_code_consumed() -> None:
    admin_user = _superuser(username="su-rec", email="su-rec@example.com")
    codes = replace_recovery_codes(admin_user)
    code = codes[0]
    assert unused_recovery_code_count(admin_user) == 10

    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/?mode=recovery",
        {
            "mode": "recovery",
            "username": admin_user.email,
            "recovery_code": code,
            "next": "/admin/",
        },
    )
    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert unused_recovery_code_count(admin_user) == 9

    # Reuse rejected.
    client2 = Client()
    again = _csrf_post(
        client2,
        "/admin/login/?mode=recovery",
        {
            "mode": "recovery",
            "username": admin_user.email,
            "recovery_code": code,
            "next": "/admin/",
        },
    )
    assert again.status_code == 200
    assert client2.session.get("_auth_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_non_superuser_recovery_rejected() -> None:
    staff = _staff_non_super(username="mgr-rec", email="mgr-rec@example.com")
    # Even if codes somehow exist, consume_recovery_code refuses non-superuser.
    SuperuserRecoveryCode.objects.create(
        user=staff,
        code_hash=hash_recovery_code("ABCD-EFGH"),
    )
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/?mode=recovery",
        {
            "mode": "recovery",
            "username": staff.username,
            "recovery_code": "ABCD-EFGH",
            "next": "/admin/",
        },
    )
    assert response.status_code == 200
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_smtp_fail_opens_otp_for_superuser_recovery() -> None:
    admin_user = _superuser(username="su-smtp", email="su-smtp@example.com")
    codes = replace_recovery_codes(admin_user)
    client = Client()
    with patch(
        "config.admin_otp.send_admin_otp_email",
        side_effect=RuntimeError("smtp down"),
    ):
        response = _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    assert response.status_code == 302
    assert response["Location"].endswith("/admin/otp/")
    assert client.session.get("admin_otp_user_id") == admin_user.pk
    assert client.session.get("admin_otp_email_failed") is True
    assert len(mail.outbox) == 0

    csrf = client.cookies["csrftoken"].value
    done = client.post(
        "/admin/otp/",
        {"otp_code": codes[0], "csrfmiddlewaretoken": csrf},
    )
    assert done.status_code == 302
    assert client.session.get("_auth_user_id") == str(admin_user.pk)
    assert unused_recovery_code_count(admin_user) == 9


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_smtp_fail_still_blocks_non_superuser() -> None:
    staff = _staff_non_super(username="mgr-smtp", email="mgr-smtp@example.com")
    client = Client()
    with patch(
        "config.admin_otp.send_admin_otp_email",
        side_effect=RuntimeError("smtp down"),
    ):
        response = _csrf_post(
            client,
            "/admin/login/",
            {"username": staff.username, "next": "/admin/"},
        )
    assert response.status_code == 200
    assert client.session.get("admin_otp_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_recovery_on_otp_page_after_email_otp() -> None:
    admin_user = _superuser(username="su-both", email="su-both@example.com")
    codes = replace_recovery_codes(admin_user)
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="424242"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.email, "next": "/admin/"},
        )
    assert len(mail.outbox) == 1
    csrf = client.cookies["csrftoken"].value
    done = client.post(
        "/admin/otp/",
        {"otp_code": codes[1], "csrfmiddlewaretoken": csrf},
    )
    assert done.status_code == 302
    assert client.session.get("_auth_user_id") == str(admin_user.pk)


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_replace_recovery_codes_invalidates_old() -> None:
    admin_user = _superuser(username="su-regen", email="su-regen@example.com")
    first = replace_recovery_codes(admin_user)
    second = replace_recovery_codes(admin_user)
    assert first[0] != second[0] or first != second
    assert not consume_recovery_code(admin_user, first[0])
    assert consume_recovery_code(admin_user, second[0])
    assert unused_recovery_code_count(admin_user) == 9


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_generate_recovery_codes_admin_view() -> None:
    admin_user = _superuser(username="su-ui", email="su-ui@example.com")
    client = Client()
    assert client.login(username=admin_user.username, password="password12")
    url = reverse("admin:auth_user_generate_recovery_codes", args=[admin_user.pk])
    get_page = client.get(url)
    assert get_page.status_code == 200
    assert "Сгенерировать" in get_page.content.decode()

    post = client.post(url)
    assert post.status_code == 200
    assert unused_recovery_code_count(admin_user) == 10
    # Plaintext shown once on the page.
    body = post.content.decode()
    assert "-" in body
    assert "один раз" in body.lower() or "только сейчас" in body.lower()


def test_normalize_recovery_helpers() -> None:
    assert normalize_recovery_code("ab cd-efgh") == "ABCD-EFGH"
    assert normalize_recovery_code("ABCDEFGH") == "ABCD-EFGH"
    assert len(hash_recovery_code("ABCD-EFGH")) == 64
