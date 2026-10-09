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
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.http import HttpRequest
from django.template.loader import render_to_string

from config.client_ip import client_ip

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


def admin_email_otp_enabled() -> bool:
    """True when Admin login uses email OTP instead of password."""
    return bool(getattr(settings, "ADMIN_EMAIL_OTP_ENABLED", False))


def otp_ttl_seconds(prefix: str = "ADMIN_EMAIL_OTP") -> int:
    """Challenge lifetime in seconds (prefix selects the OTP scope)."""
    return int(getattr(settings, f"{prefix}_TTL_SECONDS", 300))


def otp_max_attempts(prefix: str = "ADMIN_EMAIL_OTP") -> int:
    """Max wrong-code tries per challenge."""
    return int(getattr(settings, f"{prefix}_MAX_ATTEMPTS", 5))


def otp_resend_cooldown_seconds(prefix: str = "ADMIN_EMAIL_OTP") -> int:
    """Minimum seconds between resend requests."""
    return int(getattr(settings, f"{prefix}_RESEND_COOLDOWN_SECONDS", 60))


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


def otp_ttl_human(prefix: str = "ADMIN_EMAIL_OTP") -> str:
    """Human TTL for email footer (e.g. «1 мин.» / «45 сек.»)."""
    ttl = max(1, otp_ttl_seconds(prefix))
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


class OtpExpiredError(AdminOtpError):
    """No live challenge under this id."""


class OtpAttemptsExhaustedError(AdminOtpError):
    """The attempt limit was already used up; the challenge is dropped."""


class OtpCodeMismatchError(AdminOtpError):
    """Wrong code; ``remaining`` tries left."""

    def __init__(self, remaining: int) -> None:
        super().__init__("wrong code")
        self.remaining = remaining


@dataclass(frozen=True, slots=True)
class OtpChallengeStore:
    """Cache-backed OTP challenges shared by Admin, staff app and client cabinet.

    The attempt counter lives in its own key and grows via ``cache.incr``
    before the code is compared, so parallel guesses cannot all see
    «0 attempts» and slip past the limit.
    """

    key_prefix: str
    settings_prefix: str
    # False keeps the spent challenge so «resend» can issue a new code on it.
    drop_on_last_miss: bool = True

    def key(self, challenge_id: str) -> str:
        return f"{self.key_prefix}{challenge_id}"

    def _attempts_key(self, challenge_id: str) -> str:
        return f"{self.key(challenge_id)}:attempts"

    def ttl(self) -> int:
        return otp_ttl_seconds(self.settings_prefix)

    def max_attempts(self) -> int:
        return otp_max_attempts(self.settings_prefix)

    def put(self, challenge_id: str, payload: dict[str, Any], *, code: str) -> None:
        """Store ``payload`` with the hashed ``code``; resets the attempt counter."""
        cache.set_many(
            {
                self.key(challenge_id): {**payload, "code_hash": hash_otp_code(code)},
                self._attempts_key(challenge_id): 0,
            },
            timeout=self.ttl(),
        )

    def update(self, challenge_id: str, payload: dict[str, Any]) -> None:
        """Rewrite payload fields without touching the code or the counter."""
        ttl = self.ttl()
        cache.set(self.key(challenge_id), payload, timeout=ttl)
        # Keep the attempts counter alive as long as the payload so it
        # cannot expire independently and reset the brute-force guard.
        cache.touch(self._attempts_key(challenge_id), timeout=ttl)

    def get(self, challenge_id: str) -> dict[str, Any] | None:
        raw = cache.get(self.key(challenge_id))
        if not isinstance(raw, dict) or not isinstance(raw.get("code_hash"), str):
            return None
        return raw

    def attempts(self, challenge_id: str) -> int:
        try:
            return int(cache.get(self._attempts_key(challenge_id)) or 0)
        except (TypeError, ValueError):
            return 0

    def register_attempt(self, challenge_id: str) -> int:
        """Atomically count one more try and return the new total."""
        counter = self._attempts_key(challenge_id)
        try:
            return int(cache.incr(counter))
        except ValueError:
            cache.add(counter, 0, timeout=self.ttl())
            return int(cache.incr(counter))

    def drop(self, challenge_id: str) -> None:
        cache.delete_many([self.key(challenge_id), self._attempts_key(challenge_id)])

    def verify(self, challenge_id: str, code: str) -> dict[str, Any]:
        """Return the payload for a correct ``code`` and drop the challenge.

        Raises:
            OtpExpiredError: Nothing stored under ``challenge_id``.
            OtpAttemptsExhaustedError: Limit already used up before this try.
            OtpCodeMismatchError: Wrong code (last miss drops it if ``drop_on_last_miss``).
        """
        payload = self.get(challenge_id)
        if payload is None:
            raise OtpExpiredError("expired")
        attempts = self.register_attempt(challenge_id)
        limit = self.max_attempts()
        if attempts > limit:
            self.drop(challenge_id)
            raise OtpAttemptsExhaustedError("attempts exhausted")
        if not hmac.compare_digest(str(payload["code_hash"]), hash_otp_code(code)):
            remaining = limit - attempts
            if remaining <= 0 and self.drop_on_last_miss:
                self.drop(challenge_id)
            raise OtpCodeMismatchError(remaining)
        self.drop(challenge_id)
        return payload


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
    key = f"{cache_prefix}{client_ip(request)}"
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


_ADMIN_OTP = OtpChallengeStore(key_prefix="admin_email_otp:v1:", settings_prefix="ADMIN_EMAIL_OTP")


def _challenge_id(user_id: int, session_key: str) -> str:
    session_digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:32]
    return f"{user_id}:{session_digest}"


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
        _ADMIN_OTP.drop(_challenge_id(int(user_id), session_key))


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
    _ADMIN_OTP.put(_challenge_id(user_id, session_key), {"locked_until": 0.0}, code=code)


def _locked_until(payload: dict[str, Any]) -> float:
    try:
        return float(payload.get("locked_until") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _delay_next_try(challenge_id: str, attempts: int) -> None:
    """Progressive pause after a miss (best-effort; the limit itself is atomic)."""
    payload = _ADMIN_OTP.get(challenge_id)
    delay = _delay_after_attempts(attempts)
    if payload is not None and delay:
        _ADMIN_OTP.update(challenge_id, {**payload, "locked_until": time.time() + delay})


def _register_miss(challenge_id: str) -> int:
    attempts = _ADMIN_OTP.register_attempt(challenge_id)
    _delay_next_try(challenge_id, attempts)
    return attempts


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


def _verify_recovery_code(
    user: AbstractBaseUser,
    raw_code: str,
    challenge_id: str | None,
) -> None:
    """Accept a superuser recovery code or raise; misses count on both limiters."""
    from accounts.recovery_codes import (
        RecoveryAttempt,
        attempt_recovery_code,
        recovery_lock_seconds,
        recovery_subject,
    )

    outcome = attempt_recovery_code(user, raw_code, subject=recovery_subject(user))
    if outcome is RecoveryAttempt.OK:
        return
    if challenge_id is not None:
        _register_miss(challenge_id)
    if outcome is RecoveryAttempt.LOCKED:
        minutes = max(1, recovery_lock_seconds() // 60)
        raise AdminOtpVerifyError(f"Слишком много неверных резервных кодов. Подождите {minutes} мин.")
    raise AdminOtpVerifyError("Неверный резервный код. Введите сохранённый код формата XXXX-XXXX.")


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

    from accounts.recovery_codes import looks_like_recovery_code

    challenge_id = _challenge_id(int(user.pk), session_key)
    payload = _ADMIN_OTP.get(challenge_id)
    now = time.time()
    if payload is not None and _locked_until(payload) > now:
        wait = max(1, int(math.ceil(_locked_until(payload) - now)))
        raise AdminOtpVerifyError(f"Подождите {wait} сек. перед следующей попыткой.")
    if payload is not None and _ADMIN_OTP.attempts(challenge_id) >= _ADMIN_OTP.max_attempts():
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Слишком много попыток. Войдите снова.")

    # Superuser may paste a saved recovery code even when email OTP is missing/wrong.
    if getattr(user, "is_superuser", False) and looks_like_recovery_code(raw_code):
        _verify_recovery_code(user, raw_code, challenge_id if payload is not None else None)
        clear_admin_otp_challenge(request)
        return user, next_url

    if payload is None:
        if pending_otp_email_failed(request) and getattr(user, "is_superuser", False):
            raise AdminOtpVerifyError(
                "Неверный резервный код. Введите сохранённый код формата XXXX-XXXX.",
            )
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Код истёк. Войдите снова.")

    code = normalize_otp_input(raw_code)
    if len(code) != _OTP_DIGITS:
        _register_miss(challenge_id)
        raise AdminOtpVerifyError(
            f"Введите {_OTP_DIGITS}-значный код из письма или резервный код супер-админа (XXXX-XXXX).",
        )

    try:
        _ADMIN_OTP.verify(challenge_id, code)
    except OtpExpiredError:
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Код истёк. Войдите снова.") from None
    except OtpAttemptsExhaustedError:
        clear_admin_otp_challenge(request)
        raise AdminOtpVerifyError("Слишком много попыток. Войдите снова.") from None
    except OtpCodeMismatchError as exc:
        if exc.remaining <= 0:
            clear_admin_otp_challenge(request)
            raise AdminOtpVerifyError("Слишком много попыток. Войдите снова.") from None
        _delay_next_try(challenge_id, _ADMIN_OTP.max_attempts() - exc.remaining)
        raise AdminOtpVerifyError(f"Неверный код. Осталось попыток: {exc.remaining}.") from None

    clear_admin_otp_challenge(request)
    return user, next_url
