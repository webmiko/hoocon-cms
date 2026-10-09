"""Cache-based OTP challenges for staff mobile (no Django session cookie)."""

from __future__ import annotations

import logging
import secrets
import time

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import User
from django.http import HttpRequest

from config.admin_otp import (
    AdminOtpDeliveryError,
    AdminOtpVerifyError,
    OtpAttemptsExhaustedError,
    OtpChallengeStore,
    OtpCodeMismatchError,
    OtpExpiredError,
    consume_otp_request_quota,
    find_staff_user_for_otp,
    generate_otp_code,
    mask_email,
    otp_resend_cooldown_seconds,
)

logger = logging.getLogger(__name__)

_STORE = OtpChallengeStore(
    key_prefix="staff_api_otp:v1:",
    settings_prefix="ADMIN_EMAIL_OTP",
    drop_on_last_miss=False,
)


def staff_api_enabled() -> bool:
    """True when ``/api/staff/`` is enabled."""
    from django.conf import settings

    return bool(getattr(settings, "STAFF_API_ENABLED", False))


def _public_email_mask(login: str) -> str:
    """Mask derived from the typed login only, so real and decoy replies match."""
    raw = (login or "").strip()
    return mask_email(raw.lower()) if "@" in raw else ""


def _staff_app_user(login: str) -> User | None:
    """Active staff with manager/admin role for ``login``, else None."""
    from accounts.roles import GROUP_ADMIN, GROUP_MANAGER

    user = find_staff_user_for_otp(login)
    if not isinstance(user, User):
        return None
    if user.is_superuser:
        return user
    names = set(user.groups.values_list("name", flat=True))
    return user if GROUP_MANAGER in names or GROUP_ADMIN in names else None


def start_staff_otp(request: HttpRequest, login: str) -> dict[str, str]:
    """Send OTP and return challenge_id + masked email.

    Unknown or role-less logins get a decoy challenge with the same reply
    (no email is sent; verify then fails as «Неверный код»), so the endpoint
    does not reveal which logins exist.
    """
    from django.conf import settings

    consume_otp_request_quota(
        request,
        cache_prefix="staff_api_otp:req_v1:",
        limit=int(getattr(settings, "STAFF_OTP_REQUEST_LIMIT", 30)),
        window=int(getattr(settings, "STAFF_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    user = _staff_app_user(login)
    code = generate_otp_code()
    challenge_id = secrets.token_urlsafe(24)
    payload = {"user_id": user.pk if user is not None else None, "sent_at": time.time()}
    _STORE.put(challenge_id, payload, code=code)
    if user is not None:
        _send_otp_email(user, code)
    return {"challenge_id": challenge_id, "email_masked": _public_email_mask(login)}


def resend_staff_otp(request: HttpRequest, challenge_id: str) -> None:
    """Resend code for an existing challenge (decoys only refresh the timer)."""
    from django.conf import settings

    consume_otp_request_quota(
        request,
        cache_prefix="staff_api_otp:req_v1:",
        limit=int(getattr(settings, "STAFF_OTP_REQUEST_LIMIT", 30)),
        window=int(getattr(settings, "STAFF_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    raw = _STORE.get(challenge_id)
    if raw is None:
        raise AdminOtpDeliveryError("Сессия входа истекла. Запросите код снова.")
    sent_at = float(raw.get("sent_at") or 0)
    if time.time() - sent_at < otp_resend_cooldown_seconds():
        raise AdminOtpDeliveryError("Подождите перед повторной отправкой.")
    user = None
    if raw.get("user_id") is not None:
        user = User.objects.filter(pk=raw["user_id"], is_active=True, is_staff=True).first()
        if user is None:
            _STORE.drop(challenge_id)
            raise AdminOtpDeliveryError("Сессия входа истекла. Запросите код снова.")
    code = generate_otp_code()
    _STORE.put(challenge_id, {**raw, "sent_at": time.time()}, code=code)
    if user is not None:
        _send_otp_email(user, code)


def verify_staff_otp(challenge_id: str, raw_code: str) -> User:
    """Validate code; return staff user. Deletes challenge on success."""
    try:
        raw = _STORE.verify(challenge_id, raw_code)
    except OtpExpiredError:
        raise AdminOtpVerifyError("Код истёк. Запросите новый.") from None
    except OtpAttemptsExhaustedError:
        raise AdminOtpVerifyError("Слишком много попыток. Запросите новый код.") from None
    except OtpCodeMismatchError:
        raise AdminOtpVerifyError("Неверный код.") from None
    from django.contrib.auth import get_user_model

    user_id = raw.get("user_id")
    user = (
        get_user_model().objects.filter(pk=user_id, is_active=True, is_staff=True).first()
        if user_id is not None
        else None
    )
    if user is None:
        raise AdminOtpVerifyError("Учётная запись недоступна.")
    return user


def _send_otp_email(user: AbstractBaseUser, code: str) -> None:
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        raise AdminOtpDeliveryError("У учётной записи нет email.")
    from config.admin_otp import send_admin_otp_email

    try:
        send_admin_otp_email(to_email=email, code=code)
    except Exception as exc:
        logger.exception("staff OTP email failed")
        raise AdminOtpDeliveryError("Не удалось отправить письмо с кодом.") from exc
