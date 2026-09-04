"""Email OTP for Django Admin login (passwordless when enabled).

Ported from lms-backend ``config/admin_otp.py``: 6-digit code, hash+pepper,
cache challenge, TTL / attempts / resend cooldown. Hoocon uses passwordless
request-code (username/email → code) instead of password+OTP 2FA.

Hardening: short TTL, email allowlist, progressive verify delay, IP request
rate limit (axes remains for long IP lockout).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import re
import secrets
import time
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.http import HttpRequest
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SESSION_USER_ID = "admin_otp_user_id"
SESSION_NEXT = "admin_otp_next"
SESSION_SENT_AT = "admin_otp_sent_at"
# True when challenge was opened without an emailed code (SMTP fail / recovery-only).
SESSION_EMAIL_FAILED = "admin_otp_email_failed"

_OTP_DIGITS = 6
_MASK_LOCAL_KEEP = 1
# Seconds to wait after 1st, 2nd, … wrong attempt before the next try is allowed.
_PROGRESSIVE_DELAYS_SEC: tuple[int, ...] = (0, 2, 5, 10, 20)


class AdminOtpError(Exception):
    """Base OTP challenge error."""


class AdminOtpDeliveryError(AdminOtpError):
    """Code could not be emailed."""


class AdminOtpVerifyError(AdminOtpError):
    """Code rejected (wrong, expired, or attempts exhausted)."""


@dataclass(frozen=True, slots=True)
class AdminOtpChallenge:
    """Cached challenge payload."""

    code_hash: str
    attempts: int
    locked_until: float = 0.0


def admin_email_otp_enabled() -> bool:
    """True when Admin login uses email OTP instead of password."""
    return bool(getattr(settings, "ADMIN_EMAIL_OTP_ENABLED", False))


def otp_ttl_seconds() -> int:
    """Challenge lifetime in seconds."""
    return int(getattr(settings, "ADMIN_EMAIL_OTP_TTL_SECONDS", 300))


def otp_max_attempts() -> int:
    """Max wrong-code tries per challenge."""
    return int(getattr(settings, "ADMIN_EMAIL_OTP_MAX_ATTEMPTS", 5))


def otp_resend_cooldown_seconds() -> int:
    """Minimum seconds between resend requests."""
    return int(getattr(settings, "ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS", 60))


def otp_request_limit() -> int:
    """Max OTP send/resend requests per IP per window."""
    return int(getattr(settings, "ADMIN_EMAIL_OTP_REQUEST_LIMIT", 5))


def otp_request_window_seconds() -> int:
    """Sliding window for IP OTP request rate limit."""
    return int(getattr(settings, "ADMIN_EMAIL_OTP_REQUEST_WINDOW_SECONDS", 600))


def otp_allowed_emails() -> frozenset[str]:
    """Lowercased allowlist entries; empty means any active staff email is OK.

    Entries may be full addresses (``user@host``) or domains (``@host`` /
    ``*@host``) so every staff mailbox on that domain is allowed.
    """
    raw = str(getattr(settings, "ADMIN_EMAIL_OTP_ALLOWED_EMAILS", "") or "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def staff_email_allowed_for_otp(email: str) -> bool:
    """True if email may receive Admin OTP (allowlist empty → allow all)."""
    allowed = otp_allowed_emails()
    if not allowed:
        return True
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    if normalized in allowed:
        return True
    if "@" not in normalized:
        return False
    _, _, domain = normalized.partition("@")
    if not domain:
        return False
    return f"@{domain}" in allowed or f"*@{domain}" in allowed


def otp_ttl_human() -> str:
    """Human TTL for email footer (e.g. «1 мин.» / «45 сек.»)."""
    ttl = max(1, otp_ttl_seconds())
    if ttl < 60:
        return f"{ttl} сек."
    minutes = max(1, math.ceil(ttl / 60))
    return f"{minutes} мин."


def mask_email(email: str) -> str:
    """Mask local-part for the OTP form UI."""
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    keep = min(_MASK_LOCAL_KEEP, len(local))
    return f"{local[:keep]}***@{domain}"


def generate_otp_code() -> str:
    """Cryptographically strong 6-digit code (leading zeros kept)."""
    return f"{secrets.randbelow(10**_OTP_DIGITS):0{_OTP_DIGITS}d}"


def hash_otp_code(code: str) -> str:
    """Hash code with SECRET_KEY pepper (never store plaintext in cache)."""
    pepper = str(settings.SECRET_KEY).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(pepper)
    digest.update(b"|admin-email-otp|")
    digest.update(code.strip().encode("utf-8"))
    return digest.hexdigest()


def _client_ip(request: HttpRequest) -> str:
    """Client IP behind one reverse proxy (nginx → gunicorn)."""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        # Leftmost entry is the original client when the edge proxy appends.
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[0]
    return (request.META.get("REMOTE_ADDR") or "0.0.0.0").strip() or "0.0.0.0"


def consume_otp_request_quota(
    request: HttpRequest,
    *,
    cache_prefix: str = "admin_email_otp:req_v1:",
    limit: int | None = None,
    window: int | None = None,
) -> None:
    """Count OTP send/resend for this IP; raise if over limit."""
    resolved_limit = otp_request_limit() if limit is None else limit
    resolved_window = otp_request_window_seconds() if window is None else window
    key = f"{cache_prefix}{_client_ip(request)}"
    try:
        count = int(cache.incr(key))
    except ValueError:
        # Key missing — seed window.
        cache.add(key, 1, timeout=resolved_window)
        count = 1
        # Race: another worker may have created it.
        if cache.get(key) != 1:
            try:
                count = int(cache.incr(key))
            except ValueError:
                count = 1
    if count > resolved_limit:
        raise AdminOtpDeliveryError("Слишком много запросов. Попробуйте позже.")


def _cache_key(user_id: int, session_key: str) -> str:
    session_digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:32]
    return f"admin_email_otp:v1:{user_id}:{session_digest}"


def _ensure_session_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.create()
    key = request.session.session_key
    if not key:
        raise AdminOtpError("session key missing")
    return key


def clear_admin_otp_challenge(request: HttpRequest) -> None:
    """Drop session + cache challenge."""
    user_id = request.session.pop(SESSION_USER_ID, None)
    request.session.pop(SESSION_NEXT, None)
    request.session.pop(SESSION_SENT_AT, None)
    request.session.pop(SESSION_EMAIL_FAILED, None)
    session_key = request.session.session_key
    if user_id is not None and session_key:
        cache.delete(_cache_key(int(user_id), session_key))


def pending_otp_email_failed(request: HttpRequest) -> bool:
    """True when pending challenge has no emailed OTP (SMTP failed for superuser)."""
    return bool(request.session.get(SESSION_EMAIL_FAILED))


def begin_admin_otp_session(
    request: HttpRequest,
    user: AbstractBaseUser,
    *,
    next_url: str,
    email_failed: bool = False,
) -> None:
    """Stash pending staff user in session without (re)sending an email OTP."""
    _ensure_session_key(request)
    request.session[SESSION_USER_ID] = user.pk
    request.session[SESSION_NEXT] = next_url
    request.session[SESSION_SENT_AT] = time.time()
    if email_failed:
        request.session[SESSION_EMAIL_FAILED] = True
    else:
        request.session.pop(SESSION_EMAIL_FAILED, None)
    request.session.modified = True


def pending_admin_otp_user_id(request: HttpRequest) -> int | None:
    """Pending staff user id from session, or None."""
    raw = request.session.get(SESSION_USER_ID)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def get_pending_admin_otp_user(request: HttpRequest) -> AbstractBaseUser | None:
    """Active staff user for the pending challenge, or None."""
    user_model = get_user_model()
    user_id = pending_admin_otp_user_id(request)
    if user_id is None:
        return None
    try:
        user = user_model.objects.get(pk=user_id)
    except user_model.DoesNotExist:
        clear_admin_otp_challenge(request)
        return None
    if not user.is_active or not user.is_staff:
        clear_admin_otp_challenge(request)
        return None
    return user


def find_staff_user_for_otp(login: str) -> AbstractBaseUser | None:
    """Resolve active staff by username or email (case-insensitive email)."""
    raw = (login or "").strip()
    if not raw:
        return None
    user_model = get_user_model()
    qs = user_model.objects.filter(is_active=True, is_staff=True)
    user = qs.filter(username__iexact=raw).first()
    if user is None and "@" in raw:
        user = qs.filter(email__iexact=raw).first()
    if user is None:
        return None
    email = (getattr(user, "email", "") or "").strip()
    if not staff_email_allowed_for_otp(email):
        return None
    return user


def _store_challenge(user_id: int, session_key: str, code: str) -> None:
    payload = {"code_hash": hash_otp_code(code), "attempts": 0, "locked_until": 0.0}
    cache.set(_cache_key(user_id, session_key), payload, timeout=otp_ttl_seconds())


def _load_challenge(user_id: int, session_key: str) -> AdminOtpChallenge | None:
    raw = cache.get(_cache_key(user_id, session_key))
    if not isinstance(raw, dict):
        return None
    code_hash = raw.get("code_hash")
    attempts = raw.get("attempts", 0)
    locked_until = raw.get("locked_until", 0.0)
    if not isinstance(code_hash, str):
        return None
    try:
        attempts_int = int(attempts)
        locked_f = float(locked_until or 0.0)
    except (TypeError, ValueError):
        return None
    return AdminOtpChallenge(
        code_hash=code_hash,
        attempts=attempts_int,
        locked_until=locked_f,
    )


def _delay_after_attempts(attempts: int) -> int:
    if attempts <= 0:
        return 0
    idx = min(attempts, len(_PROGRESSIVE_DELAYS_SEC) - 1)
    return _PROGRESSIVE_DELAYS_SEC[idx]


def send_admin_otp_email(*, to_email: str, code: str) -> None:
    """Plain + HTML mail with the one-time code (manual entry, no magic link)."""
    site_url = str(getattr(settings, "SITE_URL", "https://hoocon.ru")).rstrip("/")
    site_name = "Hoocon"
    subject = f"Код входа в админку — {site_name}"
    intro = "Ваш одноразовый код для входа в панель управления:"
    footer = f"Код действует {otp_ttl_human()} Если вы не пытались войти — проигнорируйте письмо."
    plain_body = f"{intro}\n\n{code}\n\n{footer}\n{site_url}\n"
    html_body = render_to_string(
        "email/admin_otp.html",
        {
            "intro": intro,
            "code": code,
            "footer": footer,
            "site_name": site_name,
            "site_url": site_url,
        },
    )
    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@hoocon.ru").strip()
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=from_email,
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.extra_headers = {"Auto-Submitted": "auto-generated"}
    msg.send(fail_silently=False)


def start_admin_otp_challenge(
    request: HttpRequest,
    user: AbstractBaseUser,
    *,
    next_url: str,
) -> None:
    """Create challenge, stash uid in session, email the code."""
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        raise AdminOtpDeliveryError("У пользователя нет email для OTP.")
    if not staff_email_allowed_for_otp(email):
        raise AdminOtpDeliveryError("Не удалось отправить код на email.")

    session_key = _ensure_session_key(request)
    code = generate_otp_code()
    try:
        send_admin_otp_email(to_email=email, code=code)
    except Exception as exc:
        logger.exception("Admin OTP email failed for user pk=%s", user.pk)
        raise AdminOtpDeliveryError("Не удалось отправить код на email.") from exc

    _store_challenge(int(user.pk), session_key, code)
    begin_admin_otp_session(request, user, next_url=next_url, email_failed=False)
    logger.info("Admin OTP challenge started for user pk=%s", user.pk)


def resend_admin_otp(request: HttpRequest) -> None:
    """Send a fresh code for the pending challenge."""
    user = get_pending_admin_otp_user(request)
    if user is None:
        raise AdminOtpVerifyError("Сессия подтверждения истекла. Войдите снова.")

    sent_at = request.session.get(SESSION_SENT_AT)
    if isinstance(sent_at, (int, float)):
        elapsed = time.time() - float(sent_at)
        cooldown = otp_resend_cooldown_seconds()
        if elapsed < cooldown:
            wait = int(cooldown - elapsed) + 1
            raise AdminOtpVerifyError(f"Повторная отправка через {wait} сек.")

    email = (getattr(user, "email", "") or "").strip()
    if not email:
        raise AdminOtpDeliveryError("У пользователя нет email для OTP.")
    if not staff_email_allowed_for_otp(email):
        raise AdminOtpDeliveryError("Не удалось отправить код на email.")

    session_key = _ensure_session_key(request)
    code = generate_otp_code()
    try:
        send_admin_otp_email(to_email=email, code=code)
    except Exception as exc:
        logger.exception("Admin OTP resend failed for user pk=%s", user.pk)
        raise AdminOtpDeliveryError("Не удалось отправить код на email.") from exc

    _store_challenge(int(user.pk), session_key, code)
    request.session[SESSION_SENT_AT] = time.time()
    request.session.pop(SESSION_EMAIL_FAILED, None)
    request.session.modified = True


def normalize_otp_input(raw: str) -> str:
    """Keep digits only (ignore spaces/dashes)."""
    return re.sub(r"\D", "", raw or "")


def peek_admin_otp_next_url(request: HttpRequest, *, fallback: str) -> str:
    """Safe Admin-relative next path from session (never public SPA URLs)."""
    raw = request.session.get(SESSION_NEXT)
    if isinstance(raw, str) and raw.startswith("/admin") and not raw.startswith("//"):
        return raw
    return fallback


def _try_recovery_code(user: AbstractBaseUser, raw_code: str) -> bool:
    """Consume a superuser recovery code when present; False if unused / invalid."""
    if not getattr(user, "is_superuser", False):
        return False
    from accounts.recovery_codes import consume_recovery_code

    return consume_recovery_code(user, raw_code)


def verify_admin_otp(
    request: HttpRequest,
    raw_code: str,
) -> tuple[AbstractBaseUser, str]:
    """Validate emailed OTP or superuser recovery code; return (user, next_url)."""
    user = get_pending_admin_otp_user(request)
    if user is None:
        raise AdminOtpVerifyError("Сессия подтверждения истекла. Войдите снова.")

    next_url = peek_admin_otp_next_url(request, fallback="/admin/")
    session_key = request.session.session_key
    if not session_key:
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Сессия подтверждения истекла. Войдите снова.")

    # Superuser may paste a saved recovery code even when email OTP is missing/wrong.
    if _try_recovery_code(user, raw_code):
        clear_admin_otp_challenge(request)
        return user, next_url

    challenge = _load_challenge(int(user.pk), session_key)
    email_failed = pending_otp_email_failed(request)
    if challenge is None:
        if email_failed and getattr(user, "is_superuser", False):
            raise AdminOtpVerifyError(
                "Неверный резервный код. Введите сохранённый код формата XXXX-XXXX.",
            )
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Код истёк. Войдите снова.")

    now = time.time()
    if challenge.locked_until > now:
        wait = max(1, int(math.ceil(challenge.locked_until - now)))
        raise AdminOtpVerifyError(f"Подождите {wait} сек. перед следующей попыткой.")

    if challenge.attempts >= otp_max_attempts():
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Слишком много попыток. Войдите снова.")

    code = normalize_otp_input(raw_code)
    if len(code) != _OTP_DIGITS:
        _bump_attempts(int(user.pk), session_key, challenge)
        raise AdminOtpVerifyError(
            f"Введите {_OTP_DIGITS}-значный код из письма или резервный код супер-админа (XXXX-XXXX).",
        )

    expected = challenge.code_hash
    actual = hash_otp_code(code)
    if not hmac.compare_digest(expected, actual):
        updated = _bump_attempts(int(user.pk), session_key, challenge)
        remaining = otp_max_attempts() - updated.attempts
        if remaining <= 0:
            clear_admin_otp_challenge(request)
            raise AdminOtpVerifyError("Слишком много попыток. Войдите снова.")
        raise AdminOtpVerifyError(f"Неверный код. Осталось попыток: {remaining}.")

    clear_admin_otp_challenge(request)
    return user, next_url


def _bump_attempts(
    user_id: int,
    session_key: str,
    challenge: AdminOtpChallenge,
) -> AdminOtpChallenge:
    new_attempts = challenge.attempts + 1
    delay = _delay_after_attempts(new_attempts)
    updated = AdminOtpChallenge(
        code_hash=challenge.code_hash,
        attempts=new_attempts,
        locked_until=time.time() + delay if delay else 0.0,
    )
    cache.set(
        _cache_key(user_id, session_key),
        {
            "code_hash": updated.code_hash,
            "attempts": updated.attempts,
            "locked_until": updated.locked_until,
        },
        timeout=otp_ttl_seconds(),
    )
    return updated
