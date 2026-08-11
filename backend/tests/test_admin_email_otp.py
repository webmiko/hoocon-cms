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
    client.get("/admin/login/")
    csrf = client.cookies["csrftoken"].value
    return client.post(url, {**data, "csrfmiddlewaretoken": csrf})


def _staff(*, username: str, email: str) -> object:
    return User.objects.create_superuser(
        username=username,
        email=email,
        password="password12",
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
        # No next= — must not fall through to /accounts/profile/
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.email},
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
    assert done["Location"].endswith("/admin/") or "/admin/" in done["Location"]
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
            "password": "password12",
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


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_staff_without_email_does_not_send_mail() -> None:
    User.objects.create_superuser(username="no-mail", email="", password="password12")
    client = Client()
    response = _csrf_post(
        client,
        "/admin/login/",
        {"username": "no-mail", "next": "/admin/"},
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_otp_delivery_failure_shows_error() -> None:
    admin_user = _staff(username="otp-fail", email="otp-fail@example.com")
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
    # Superuser break-glass: still open verify session for recovery code.
    assert response.status_code == 302
    assert response["Location"].endswith("/admin/otp/")
    assert client.session.get("admin_otp_user_id") == admin_user.pk
    assert client.session.get("admin_otp_email_failed") is True
    assert len(mail.outbox) == 0


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_otp_page_without_challenge_redirects_to_login() -> None:
    client = Client()
    response = client.get("/admin/otp/")
    assert response.status_code == 302
    assert response["Location"].endswith("/admin/login/")


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_otp_cancel_clears_challenge() -> None:
    admin_user = _staff(username="otp-cancel", email="otp-cancel@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="333333"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    assert client.session.get("admin_otp_user_id") == admin_user.pk
    cancelled = client.get("/admin/otp/cancel/")
    assert cancelled.status_code == 302
    assert cancelled["Location"].endswith("/admin/login/")
    assert client.session.get("admin_otp_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_otp_resend_after_cooldown_sends_new_mail() -> None:
    admin_user = _staff(username="otp-resend2", email="otp-resend2@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="444444"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    assert len(mail.outbox) == 1
    session = client.session
    session["admin_otp_sent_at"] = 0.0
    session.save()
    csrf = client.cookies["csrftoken"].value
    with patch("config.admin_otp.generate_otp_code", return_value="555555"):
        again = client.post(
            "/admin/otp/resend/",
            {"csrfmiddlewaretoken": csrf},
        )
    assert again.status_code == 302
    assert len(mail.outbox) == 2


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_otp_short_code_and_exhausted_attempts() -> None:
    admin_user = _staff(username="otp-attempts", email="otp-attempts@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="666666"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    csrf = client.cookies["csrftoken"].value
    with patch("config.admin_otp._delay_after_attempts", return_value=0):
        short = client.post(
            "/admin/otp/",
            {"otp_code": "12", "csrfmiddlewaretoken": csrf},
        )
        assert short.status_code == 200
        assert client.session.get("admin_otp_user_id") == admin_user.pk

        for _ in range(4):
            bad = client.post(
                "/admin/otp/",
                {"otp_code": "000000", "csrfmiddlewaretoken": csrf},
            )
    assert bad.status_code == 302
    assert bad["Location"].endswith("/admin/login/")
    assert client.session.get("admin_otp_user_id") is None
    assert client.session.get("_auth_user_id") is None


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_login_redirects_to_otp_when_challenge_pending() -> None:
    admin_user = _staff(username="otp-pend", email="otp-pend@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="777777"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    again = client.get("/admin/login/")
    assert again.status_code == 302
    assert again["Location"].endswith("/admin/otp/")


def test_normalize_and_mask_helpers() -> None:
    assert normalize_otp_input("12 34-56") == "123456"
    assert mask_email("ab@hoocon.ru") == "a***@hoocon.ru"
    assert mask_email("no-at") == "***"
    assert mask_email("@domain.ru") == "***@domain.ru"
    assert len(hash_otp_code("123456")) == 64


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_find_staff_and_pending_edge_cases() -> None:
    from django.test import RequestFactory

    from config.admin_otp import (
        AdminOtpVerifyError,
        _cache_key,
        _load_challenge,
        find_staff_user_for_otp,
        get_pending_admin_otp_user,
        pending_admin_otp_user_id,
        verify_admin_otp,
    )

    assert find_staff_user_for_otp("") is None
    assert find_staff_user_for_otp("not-an-email") is None
    admin_user = _staff(username="otp-edge", email="otp-edge@example.com")
    assert find_staff_user_for_otp("otp-edge").pk == admin_user.pk

    inactive = User.objects.create_user(
        username="otp-inactive",
        email="otp-inactive@example.com",
        password="password12",
        is_staff=True,
        is_active=False,
    )

    client = Client()
    factory = RequestFactory()
    session = client.session
    session["admin_otp_user_id"] = "not-int"
    session.save()
    req = factory.get("/admin/otp/")
    req.session = client.session
    assert pending_admin_otp_user_id(req) is None

    session = client.session
    session["admin_otp_user_id"] = 999999
    session.save()
    req = factory.get("/admin/otp/")
    req.session = client.session
    assert get_pending_admin_otp_user(req) is None

    session = client.session
    session["admin_otp_user_id"] = inactive.pk
    session.save()
    req = factory.get("/admin/otp/")
    req.session = client.session
    assert get_pending_admin_otp_user(req) is None

    cache.set(_cache_key(admin_user.pk, "sess"), "not-a-dict", timeout=60)
    assert _load_challenge(admin_user.pk, "sess") is None
    cache.set(_cache_key(admin_user.pk, "sess"), {"code_hash": 1}, timeout=60)
    assert _load_challenge(admin_user.pk, "sess") is None
    cache.set(
        _cache_key(admin_user.pk, "sess"),
        {"code_hash": "abc", "attempts": "x"},
        timeout=60,
    )
    assert _load_challenge(admin_user.pk, "sess") is None

    session = client.session
    session["admin_otp_user_id"] = admin_user.pk
    session.save()
    req = factory.get("/admin/otp/")
    req.session = client.session
    req.session.create()
    with pytest.raises(AdminOtpVerifyError, match="истёк|истекла"):
        verify_admin_otp(req, "123456")


@pytest.mark.django_db
@override_settings(
    **{
        **OTP_SETTINGS,
        "ADMIN_EMAIL_OTP_ALLOWED_EMAILS": "mikolamus@ya.ru,@hoocon.ru",
    },
)
def test_domain_allowlist_allows_hoocon_staff() -> None:
    blocked = _staff(username="blocked", email="blocked@example.com")
    allowed = _staff(username="assistant", email="assistant@hoocon.ru")
    client = Client()
    blocked_resp = _csrf_post(
        client,
        "/admin/login/",
        {"username": blocked.username, "next": "/admin/"},
    )
    assert blocked_resp.status_code == 200
    assert len(mail.outbox) == 0

    ok_resp = _csrf_post(
        client,
        "/admin/login/",
        {"username": allowed.username, "next": "/admin/"},
    )
    assert ok_resp.status_code == 302
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(
    **{
        **OTP_SETTINGS,
        "ADMIN_EMAIL_OTP_ALLOWED_EMAILS": "allowed@example.com",
    },
)
def test_allowlist_blocks_other_staff_email() -> None:
    _staff(username="blocked", email="blocked@example.com")
    allowed = _staff(username="ok-user", email="allowed@example.com")
    client = Client()
    blocked_resp = _csrf_post(
        client,
        "/admin/login/",
        {"username": "blocked", "next": "/admin/"},
    )
    assert blocked_resp.status_code == 200
    assert len(mail.outbox) == 0

    ok_resp = _csrf_post(
        client,
        "/admin/login/",
        {"username": allowed.username, "next": "/admin/"},
    )
    assert ok_resp.status_code == 302
    assert len(mail.outbox) == 1
    assert "5 мин" in mail.outbox[0].body


@pytest.mark.django_db
@override_settings(
    **{
        **OTP_SETTINGS,
        "ADMIN_EMAIL_OTP_REQUEST_LIMIT": 2,
        "ADMIN_EMAIL_OTP_REQUEST_WINDOW_SECONDS": 600,
    },
)
def test_otp_request_rate_limit_by_ip() -> None:
    admin_user = _staff(username="otp-rate", email="otp-rate@example.com")
    client = Client(REMOTE_ADDR="203.0.113.50")
    with patch("config.admin_otp.generate_otp_code", return_value="121212"):
        r1 = _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
        assert r1.status_code == 302
        client.get("/admin/otp/cancel/")
        r2 = _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
        assert r2.status_code == 302
        client.get("/admin/otp/cancel/")
        r3 = _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    assert r3.status_code == 200
    assert len(mail.outbox) == 2


@pytest.mark.django_db
@override_settings(**OTP_SETTINGS)
def test_progressive_delay_blocks_immediate_retry() -> None:
    admin_user = _staff(username="otp-delay", email="otp-delay@example.com")
    client = Client()
    with patch("config.admin_otp.generate_otp_code", return_value="131313"):
        _csrf_post(
            client,
            "/admin/login/",
            {"username": admin_user.username, "next": "/admin/"},
        )
    csrf = client.cookies["csrftoken"].value
    first = client.post(
        "/admin/otp/",
        {"otp_code": "000000", "csrfmiddlewaretoken": csrf},
    )
    assert first.status_code == 200
    assert "Неверный код" in first.content.decode()
    second = client.post(
        "/admin/otp/",
        {"otp_code": "000000", "csrfmiddlewaretoken": csrf},
    )
    assert second.status_code == 200
    assert "Подождите" in second.content.decode()


def test_otp_ttl_human_and_allowlist_helpers() -> None:
    from config.admin_otp import otp_ttl_human, staff_email_allowed_for_otp

    with override_settings(ADMIN_EMAIL_OTP_TTL_SECONDS=300):
        assert otp_ttl_human() == "5 мин."
    with override_settings(ADMIN_EMAIL_OTP_TTL_SECONDS=60):
        assert otp_ttl_human() == "1 мин."
    with override_settings(ADMIN_EMAIL_OTP_TTL_SECONDS=45):
        assert otp_ttl_human() == "45 сек."
    with override_settings(ADMIN_EMAIL_OTP_ALLOWED_EMAILS=""):
        assert staff_email_allowed_for_otp("any@x.ru") is True
    with override_settings(ADMIN_EMAIL_OTP_ALLOWED_EMAILS="A@X.ru, b@y.ru"):
        assert staff_email_allowed_for_otp("a@x.ru") is True
        assert staff_email_allowed_for_otp("other@x.ru") is False
    with override_settings(ADMIN_EMAIL_OTP_ALLOWED_EMAILS="mikolamus@ya.ru,@hoocon.ru"):
        assert staff_email_allowed_for_otp("assistant@hoocon.ru") is True
        assert staff_email_allowed_for_otp("sales@HOOCON.ru") is True
        assert staff_email_allowed_for_otp("other@example.com") is False
        assert staff_email_allowed_for_otp("mikolamus@ya.ru") is True
    with override_settings(ADMIN_EMAIL_OTP_ALLOWED_EMAILS="*@hoocon.ru"):
        assert staff_email_allowed_for_otp("a@hoocon.ru") is True
        assert staff_email_allowed_for_otp("a@other.ru") is False


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()
    yield
    cache.clear()
