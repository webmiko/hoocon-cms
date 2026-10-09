"""Client cabinet services: registration/login (A/B), OTP, linking, repeats."""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string

from accounts.models import ClientAccount, ClientAuthMode
from config.admin_otp import (
    AdminOtpError,
    OtpAttemptsExhaustedError,
    OtpChallengeStore,
    OtpExpiredError,
    consume_otp_request_quota,
    generate_otp_code,
    mask_email,
    otp_resend_cooldown_seconds,
    otp_ttl_human,
)
from config.pdn import PDN_CONSENT_REQUIRED, stamp_pdn_consent
from crm.models import Client

logger = logging.getLogger(__name__)

_OTP = OtpChallengeStore(key_prefix="client_otp:v1:", settings_prefix="CLIENT_OTP")
_OTP_REQ_PREFIX = "client_otp:req_v1:"


class ClientAuthError(Exception):
    """User-facing auth failure (неверные данные, код, лимит)."""


class ClientRateLimitError(ClientAuthError):
    """Too many code requests from this address (HTTP 429)."""


def normalize_client_email(raw: str) -> str:
    """Normalize + validate a client email (lowercase, RFC shape)."""
    email = (raw or "").strip().lower()
    if not email:
        raise ClientAuthError("Укажите эл. почту.")
    try:
        validate_email(email)
    except ValidationError as exc:
        raise ClientAuthError("Некорректная эл. почта.") from exc
    return email


def _min_fill_seconds() -> int:
    return int(getattr(settings, "CLIENT_AUTH_MIN_FILL_SECONDS", 2))


def _max_form_age_seconds() -> int:
    return int(getattr(settings, "CLIENT_AUTH_MAX_FORM_AGE_SECONDS", 24 * 60 * 60))


def check_honeypot(request: HttpRequest, form_start_ts: Any, trap_value: str) -> None:
    """Anti-bot guard for register/OTP forms: honeypot + fill-time window.

    Own stack per security-baseline (no third-party CAPTCHA). Trap value is
    a field bots fill and humans never see; ``form_start_ts`` marks when the
    form was rendered. A missing, future, too-fast or day-old stamp is a bot.
    """
    if (trap_value or "").strip():
        raise ClientAuthError("Запрос отклонён.")
    try:
        started = float(form_start_ts or 0)
    except (TypeError, ValueError):
        raise ClientAuthError("Запрос отклонён.") from None
    elapsed = time.time() - started
    if started <= 0 or elapsed < _min_fill_seconds() or elapsed > _max_form_age_seconds():
        raise ClientAuthError("Запрос отклонён.")


def start_client_registration(
    request: HttpRequest,
    *,
    email: str,
    password: str,
    name: str = "",
    phone: str = "",
    pdn_consent: bool = False,
) -> dict[str, str]:
    """Mode A step 1: email a code; the account appears only after verify.

    The password waits hashed in the challenge, so nobody can pre-register
    someone else's address and keep a password on the verified account.
    An existing verified account gets a plain login code — same response,
    no enumeration, password untouched.
    """
    email = normalize_client_email(email)
    if len(password or "") < 8:
        raise ClientAuthError("Пароль — минимум 8 символов.")
    existing = ClientAccount.objects.filter(email=email).first()
    if existing is not None and not existing.is_active:
        raise ClientAuthError("Аккаунт недоступен. Обратитесь к менеджеру.")
    pending: dict[str, str] | None = None
    if existing is None or existing.email_verified_at is None:
        pending = {
            "password_hash": make_password(password),
            "name": (name or "").strip(),
            "phone": (phone or "").strip(),
        }
    return _issue_challenge(request, email=email, pending=pending, pdn_consent=pdn_consent)


def authenticate_password(*, email: str, password: str) -> ClientAccount:
    """Mode A login: verify email + password (uniform error, no enumeration).

    Accounts whose email was never verified cannot use a password — it was
    set by whoever typed the address, not necessarily its owner.
    """
    email = normalize_client_email(email)
    try:
        account = ClientAccount.objects.get(email=email, is_active=True)
    except ClientAccount.DoesNotExist as exc:
        raise ClientAuthError("Неверная почта или пароль.") from exc
    if not account.check_password(password or ""):
        raise ClientAuthError("Неверная почта или пароль.")
    if account.email_verified_at is None:
        raise ClientAuthError("Подтвердите почту: войдите по коду из письма.")
    return account


def start_client_otp(request: HttpRequest, email: str, *, pdn_consent: bool = False) -> dict[str, str]:
    """Mode B step 1: email a fresh 6-digit code; return challenge id.

    No account or CRM card is created here — only after the code proves
    the visitor owns the address (:func:`verify_client_otp`).
    """
    email = normalize_client_email(email)
    if ClientAccount.objects.filter(email=email, is_active=False).exists():
        raise ClientAuthError("Аккаунт недоступен. Обратитесь к менеджеру.")
    return _issue_challenge(request, email=email, pending=None, pdn_consent=pdn_consent)


def verify_client_otp(*, challenge_id: str, code: str) -> ClientAccount:
    """Step 2 for both modes: validate code → verified, linked account."""
    try:
        payload = _OTP.verify(challenge_id, (code or "").strip())
    except OtpExpiredError:
        raise ClientAuthError("Код истёк — запросите новый.") from None
    except OtpAttemptsExhaustedError:
        raise ClientAuthError("Превышено число попыток — запросите новый код.") from None
    except AdminOtpError:
        raise ClientAuthError("Неверный код.") from None
    return _account_for_verified_email(payload)


def resend_client_otp(request: HttpRequest, challenge_id: str) -> dict[str, str]:
    """Re-send the OTP email honouring the resend cooldown."""
    payload = _OTP.get(challenge_id)
    if payload is None:
        raise ClientAuthError("Код истёк — запросите новый.")
    now = time.time()
    if now < payload["resend_after"]:
        raise ClientAuthError("Подождите перед повторной отправкой.")
    _consume_quota(request)
    code = generate_otp_code()
    payload = {**payload, "sent_at": now, "resend_after": now + otp_resend_cooldown_seconds("CLIENT_OTP")}
    _OTP.put(challenge_id, payload, code=code)
    _send_client_otp_email(email=payload["email"], code=code)
    return {"challenge_id": challenge_id, "email_masked": mask_email(payload["email"])}


def _consume_quota(request: HttpRequest) -> None:
    try:
        consume_otp_request_quota(
            request,
            cache_prefix=_OTP_REQ_PREFIX,
            limit=int(getattr(settings, "CLIENT_OTP_REQUEST_LIMIT", 20)),
            window=int(getattr(settings, "CLIENT_OTP_REQUEST_WINDOW_SECONDS", 3600)),
        )
    except AdminOtpError as exc:
        raise ClientRateLimitError(str(exc)) from exc


def _issue_challenge(
    request: HttpRequest,
    *,
    email: str,
    pending: dict[str, str] | None,
    pdn_consent: bool = False,
) -> dict[str, str]:
    """Store a fresh code challenge for ``email`` and send the letter."""
    _consume_quota(request)
    code = generate_otp_code()
    challenge_id = secrets.token_urlsafe(24)
    now = time.time()
    _OTP.put(
        challenge_id,
        {
            "email": email,
            "pending": pending,
            "pdn_consent": bool(pdn_consent),
            "sent_at": now,
            "resend_after": now + otp_resend_cooldown_seconds("CLIENT_OTP"),
        },
        code=code,
    )
    _send_client_otp_email(email=email, code=code)
    return {"challenge_id": challenge_id, "email_masked": mask_email(email)}


def _account_for_verified_email(payload: dict[str, Any]) -> ClientAccount:
    """Create or update the account behind a proven email, then link CRM.

    A password set before verification (legacy unverified account) is
    replaced by the one from this challenge or dropped — it was never
    proven to belong to the address owner. No account is created without
    PDN consent given in the form that requested the code.
    """
    from django.utils import timezone

    email = payload["email"]
    pending = payload.get("pending") or {}
    with transaction.atomic():
        account = ClientAccount.objects.select_for_update().filter(email=email).first()
        if account is None and not payload.get("pdn_consent"):
            raise ClientAuthError(PDN_CONSENT_REQUIRED)
        if account is None:
            account = ClientAccount(
                email=email,
                auth_mode=ClientAuthMode.PASSWORD if pending else ClientAuthMode.OTP_EMAIL,
                name=pending.get("name", ""),
                phone=pending.get("phone", ""),
            )
        if not account.is_active:
            raise ClientAuthError("Аккаунт недоступен.")
        if account.email_verified_at is None:
            account.password_hash = pending.get("password_hash", "")
            if pending:
                account.auth_mode = ClientAuthMode.PASSWORD
            account.email_verified_at = timezone.now()
        if payload.get("pdn_consent"):
            stamp_pdn_consent(account)
        account.save()
        link_client_account(account)
    return account


def _otp_key(challenge_id: str) -> str:
    return _OTP.key(challenge_id)


def _send_client_otp_email(*, email: str, code: str) -> None:
    """Send the 6-digit login code (Celery task wrapper keeps request fast)."""
    from cabinet.tasks import send_client_otp_email_task

    send_client_otp_email_task.delay(email, code)


def build_client_otp_message(email: str, code: str) -> EmailMultiAlternatives:
    """Compose the OTP email (plain + HTML, no PII in subject)."""
    site_url = str(getattr(settings, "SITE_URL", "https://hoocon.ru")).rstrip("/")
    subject = "Код входа в личный кабинет — Hoocon"
    intro = "Ваш одноразовый код для входа в личный кабинет:"
    footer = f"Код действует {otp_ttl_human('CLIENT_OTP')} Если вы не пытались войти — проигнорируйте письмо."
    plain_body = f"{intro}\n\n{code}\n\n{footer}\n{site_url}\n"
    html_body = render_to_string(
        "email/admin_otp.html",
        {
            "intro": intro,
            "code": code,
            "footer": footer,
            "site_name": "Hoocon",
            "site_url": site_url,
        },
    )
    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "noreply@hoocon.ru").strip()
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=from_email,
        to=[email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.extra_headers = {"Auto-Submitted": "auto-generated"}
    return msg


def link_client_account(account: ClientAccount) -> Client:
    """Attach the CRM Client card to the account by email (both directions).

    Creating the card eagerly lets ЛК show leads issued before registration
    (they attach to the card by the same email via ``crm.services``).
    """
    from crm.services import get_or_create_client_by_email

    client = get_or_create_client_by_email(
        email=account.email,
        name=account.name,
        phone=account.phone,
    )
    if client.account_id != account.pk:
        client.account = account
        client.save(update_fields=["account", "updated_at"])
    _backfill_conversations(client)
    return client


def _backfill_conversations(client: Client) -> None:
    """Attach orphan support threads with the client's contact email.

    Web dialogs link at start via ``_auto_link_client``; this sweep heals
    conversations created before that rule (and messenger threads where
    staff filled ``contact_email`` manually) whenever the client account
    is used.
    """
    from supportchat.models import Conversation

    Conversation.objects.filter(
        client__isnull=True,
        contact_email__iexact=client.email,
    ).update(client=client)
