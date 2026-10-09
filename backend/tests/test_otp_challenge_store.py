"""One OTP challenge store for Admin, staff app and client cabinet."""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings

from config.admin_otp import (
    OtpAttemptsExhaustedError,
    OtpChallengeStore,
    OtpCodeMismatchError,
    OtpExpiredError,
)

User = get_user_model()

_STORE = OtpChallengeStore(key_prefix="test_otp:v1:", settings_prefix="TEST_OTP")


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@override_settings(TEST_OTP_MAX_ATTEMPTS=3, TEST_OTP_TTL_SECONDS=300)
def test_store_counts_every_try_before_comparing() -> None:
    """Попытка считается до сравнения кода — параллельные переборы не видят «0 попыток»."""
    _STORE.put("c1", {"email": "a@example.com"}, code="123456")

    with pytest.raises(OtpCodeMismatchError) as first:
        _STORE.verify("c1", "000000")
    assert first.value.remaining == 2
    assert _STORE.attempts("c1") == 1

    assert _STORE.verify("c1", "123456")["email"] == "a@example.com"
    with pytest.raises(OtpExpiredError):
        _STORE.verify("c1", "123456")


@override_settings(TEST_OTP_MAX_ATTEMPTS=2, TEST_OTP_TTL_SECONDS=300)
def test_store_drops_challenge_on_last_wrong_try_and_on_overflow() -> None:
    _STORE.put("c2", {}, code="123456")
    with pytest.raises(OtpCodeMismatchError):
        _STORE.verify("c2", "000000")
    with pytest.raises(OtpCodeMismatchError) as last:
        _STORE.verify("c2", "000001")
    assert last.value.remaining == 0
    assert _STORE.get("c2") is None

    _STORE.put("c3", {}, code="123456")
    _STORE.register_attempt("c3")
    _STORE.register_attempt("c3")
    with pytest.raises(OtpAttemptsExhaustedError):
        _STORE.verify("c3", "123456")
    assert _STORE.get("c3") is None


@override_settings(TEST_OTP_MAX_ATTEMPTS=5, TEST_OTP_TTL_SECONDS=300)
def test_payload_rewrite_never_resets_attempt_counter() -> None:
    """Счётчик попыток — отдельный ключ: перезапись payload (задержка, гонка) его не обнуляет."""
    _STORE.put("c4", {"locked_until": 0.0}, code="123456")
    stale = _STORE.get("c4")
    for wrong in ("000000", "000001"):
        with pytest.raises(OtpCodeMismatchError):
            _STORE.verify("c4", wrong)
    assert stale is not None
    _STORE.update("c4", stale)
    assert _STORE.attempts("c4") == 2


@override_settings(TEST_OTP_MAX_ATTEMPTS=5, TEST_OTP_TTL_SECONDS=300)
def test_store_compares_code_in_constant_time() -> None:
    _STORE.put("c5", {}, code="123456")
    with patch("config.admin_otp.hmac.compare_digest", wraps=__import__("hmac").compare_digest) as spy:
        _STORE.verify("c5", "123456")
    spy.assert_called_once()


@pytest.mark.django_db
@override_settings(
    ADMIN_EMAIL_OTP_ENABLED=True,
    ADMIN_EMAIL_OTP_TTL_SECONDS=300,
    ADMIN_EMAIL_OTP_MAX_ATTEMPTS=5,
    ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS=60,
    ADMIN_EMAIL_OTP_ALLOWED_EMAILS="",
    ADMIN_EMAIL_OTP_REQUEST_LIMIT=50,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    AXES_ENABLED=False,
)
def test_admin_otp_limit_survives_stale_parallel_write() -> None:
    """Админ-OTP хранил попытки в payload через get/set — устаревшая запись соседнего запроса сбрасывала лимит."""
    from config.admin_otp import _ADMIN_OTP, _challenge_id

    user = User.objects.create_user(
        username="otp-race",
        email="otp-race@example.com",
        password="password12",
        is_staff=True,
    )
    client = Client()
    client.get("/admin/login/")
    with patch("config.admin_otp.generate_otp_code", return_value="654321"):
        client.post(
            "/admin/login/",
            {
                "username": user.username,
                "next": "/admin/",
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
    challenge_id = _challenge_id(user.pk, client.session.session_key)
    stale = _ADMIN_OTP.get(challenge_id)
    assert stale is not None
    csrf = client.cookies["csrftoken"].value

    with patch("config.admin_otp._delay_after_attempts", return_value=0):
        for _ in range(2):
            client.post("/admin/otp/", {"otp_code": "000000", "csrfmiddlewaretoken": csrf})
        _ADMIN_OTP.update(challenge_id, stale)
        for _ in range(3):
            last = client.post("/admin/otp/", {"otp_code": "000000", "csrfmiddlewaretoken": csrf})

    assert last.status_code == 302
    assert last["Location"].endswith("/admin/login/")
    assert client.session.get("_auth_user_id") is None


@override_settings(TEST_OTP_MAX_ATTEMPTS=3, TEST_OTP_TTL_SECONDS=300)
def test_update_keeps_attempts_counter_ttl_in_sync() -> None:
    """update() must refresh the :attempts TTL so it cannot expire while the payload lives.

    Bugbot finding: progressive-delay update only set payload TTL; the
    counter kept the original TTL and could expire, resetting the guard to 0.
    """
    _STORE.put("ttl-sync", {"locked_until": 0.0}, code="123456")
    with pytest.raises(OtpCodeMismatchError):
        _STORE.verify("ttl-sync", "000000")
    assert _STORE.attempts("ttl-sync") == 1
    # Simulate progressive delay writing an updated locked_until.
    payload = _STORE.get("ttl-sync")
    assert payload is not None
    _STORE.update("ttl-sync", {**payload, "locked_until": 999.0})
    # After update, the attempts counter must still be accessible.
    assert _STORE.attempts("ttl-sync") == 1
    # And cache.touch was called for the attempts key (verified by TTL surviving).
    with patch("config.admin_otp.cache.touch") as mock_touch:
        _STORE.update("ttl-sync", {**payload, "locked_until": 0.0})
        mock_touch.assert_called_once_with(_STORE._attempts_key("ttl-sync"), timeout=300)


def test_all_otp_flows_use_the_shared_store() -> None:
    """Три копии OTP (admin/staff/кабинет) расходились в атомарности и сравнении."""
    from cabinet import services as cabinet_services
    from config import admin_otp
    from staff_api import otp as staff_otp

    assert isinstance(admin_otp._ADMIN_OTP, OtpChallengeStore)
    assert isinstance(staff_otp._STORE, OtpChallengeStore)
    assert isinstance(cabinet_services._OTP, OtpChallengeStore)
    for module in (staff_otp, cabinet_services):
        source = inspect.getsource(module)
        assert "compare_digest" not in source
        assert ":attempts" not in source
    for fn in (admin_otp.verify_admin_otp, staff_otp.verify_staff_otp, cabinet_services.verify_client_otp):
        assert ".verify(" in inspect.getsource(fn), fn.__name__
