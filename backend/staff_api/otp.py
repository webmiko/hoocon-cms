"""Cache-based OTP challenges for staff mobile (no Django session cookie)."""

from __future__ import annotations

import logging
import secrets
import time

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.cache import cache
from django.http import HttpRequest

from config.admin_otp import (
    AdminOtpDeliveryError,
    AdminOtpVerifyError,
    consume_otp_request_quota,
    find_staff_user_for_otp,
    generate_otp_code,
    hash_otp_code,
    mask_email,
    otp_max_attempts,
    otp_resend_cooldown_seconds,
    otp_ttl_seconds,
)

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "staff_api_otp:v1:"


def staff_api_enabled() -> bool:
    """True when ``/api/staff/`` is enabled."""
    from django.conf import settings

    return bool(getattr(settings, "STAFF_API_ENABLED", False))


def _challenge_key(challenge_id: str) -> str:
    return f"{_CACHE_PREFIX}{challenge_id}"


def start_staff_otp(request: HttpRequest, login: str) -> dict[str, str]:
    """Send OTP and return challenge_id + masked email."""
    from django.conf import settings

    consume_otp_request_quota(
        request,
        cache_prefix="staff_api_otp:req_v1:",
        limit=int(getattr(settings, "STAFF_OTP_REQUEST_LIMIT", 30)),
        window=int(getattr(settings, "STAFF_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    user = find_staff_user_for_otp(login)
    if user is None:
        # Same shape as success to avoid user enumeration timing where possible.
        raise AdminOtpDeliveryError("Не удалось отправить код. Проверьте логин.")

    from accounts.roles import GROUP_ADMIN, GROUP_MANAGER

    if not user.is_superuser:
        names = set(user.groups.values_list("name", flat=True))
        if GROUP_MANAGER not in names and GROUP_ADMIN not in names:
            raise AdminOtpDeliveryError("Нет доступа к приложению менеджера.")

    code = generate_otp_code()
    challenge_id = secrets.token_urlsafe(24)
    payload = {
        "user_id": user.pk,
        "code_hash": hash_otp_code(code),
        "attempts": 0,
        "sent_at": time.time(),
        "email": (getattr(user, "email", "") or "") or str(user.get_username()),
    }
    cache.set(_challenge_key(challenge_id), payload, timeout=otp_ttl_seconds())
    _send_otp_email(user, code)
    return {
        "challenge_id": challenge_id,
        "email_masked": mask_email(payload["email"]),
    }


def resend_staff_otp(request: HttpRequest, challenge_id: str) -> None:
    """Resend code for an existing challenge."""
    from django.conf import settings

    consume_otp_request_quota(
        request,
        cache_prefix="staff_api_otp:req_v1:",
        limit=int(getattr(settings, "STAFF_OTP_REQUEST_LIMIT", 30)),
        window=int(getattr(settings, "STAFF_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    raw = cache.get(_challenge_key(challenge_id))
    if not isinstance(raw, dict):
        raise AdminOtpDeliveryError("Сессия входа истекла. Запросите код снова.")
    sent_at = float(raw.get("sent_at") or 0)
    if time.time() - sent_at < otp_resend_cooldown_seconds():
        raise AdminOtpDeliveryError("Подождите перед повторной отправкой.")
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=raw["user_id"], is_active=True, is_staff=True).first()
    if user is None:
        cache.delete(_challenge_key(challenge_id))
        raise AdminOtpDeliveryError("Сессия входа истекла. Запросите код снова.")
    code = generate_otp_code()
    raw["code_hash"] = hash_otp_code(code)
    raw["attempts"] = 0
    raw["sent_at"] = time.time()
    cache.set(_challenge_key(challenge_id), raw, timeout=otp_ttl_seconds())
    _send_otp_email(user, code)


def verify_staff_otp(challenge_id: str, raw_code: str) -> AbstractBaseUser:
    """Validate code; return staff user. Deletes challenge on success."""
    key = _challenge_key(challenge_id)
    raw = cache.get(key)
    if not isinstance(raw, dict):
        raise AdminOtpVerifyError("Код истёк. Запросите новый.")
    attempts = int(raw.get("attempts") or 0)
    if attempts >= otp_max_attempts():
        cache.delete(key)
        raise AdminOtpVerifyError("Слишком много попыток. Запросите новый код.")
    if not hmac_compare(raw.get("code_hash", ""), hash_otp_code(raw_code)):
        raw["attempts"] = attempts + 1
        cache.set(key, raw, timeout=otp_ttl_seconds())
        raise AdminOtpVerifyError("Неверный код.")
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(pk=raw["user_id"], is_active=True, is_staff=True).first()
    cache.delete(key)
    if user is None:
        raise AdminOtpVerifyError("Учётная запись недоступна.")
    return user


def hmac_compare(a: str, b: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest(str(a), str(b))


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
