"""Client cabinet services: registration/login (A/B), OTP, linking, repeats."""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string

from accounts.models import ClientAccount, ClientAuthMode
from config.admin_otp import (
    consume_otp_request_quota,
    generate_otp_code,
    hash_otp_code,
    mask_email,
    otp_max_attempts,
    otp_resend_cooldown_seconds,
    otp_ttl_human,
    otp_ttl_seconds,
)
from crm.models import Client

logger = logging.getLogger(__name__)

_OTP_CHALLENGE_PREFIX = "client_otp:v1:"
_OTP_REQ_PREFIX = "client_otp:req_v1:"


class ClientAuthError(Exception):
    """User-facing auth failure (неверные данные, код, лимит)."""


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


def check_honeypot(request: HttpRequest, form_start_ts: Any, trap_value: str) -> None:
    """Anti-bot guard for register/OTP forms: honeypot + min fill time.

    Own stack per security-baseline (no third-party CAPTCHA). Trap value is
    a field bots fill and humans never see; ``form_start_ts`` marks when the
    form was rendered — submissions faster than the threshold are rejected.
    """
    if (trap_value or "").strip():
        raise ClientAuthError("Запрос отклонён.")
    try:
        elapsed = time.time() - float(form_start_ts or 0)
    except (TypeError, ValueError):
        raise ClientAuthError("Запрос отклонён.") from None
    if elapsed < _min_fill_seconds():
        raise ClientAuthError("Запрос отклонён.")


def register_client(
    *,
    email: str,
    password: str,
    name: str = "",
    phone: str = "",
) -> ClientAccount:
    """Create a ClientAccount (mode A: email + password) and link CRM card."""
    email = normalize_client_email(email)
    if len(password or "") < 8:
        raise ClientAuthError("Пароль — минимум 8 символов.")
    with transaction.atomic():
        if ClientAccount.objects.filter(email=email).exists():
            raise ClientAuthError("Аккаунт с этой почтой уже существует.")
        account = ClientAccount(
            email=email,
            auth_mode=ClientAuthMode.PASSWORD,
            name=(name or "").strip(),
            phone=(phone or "").strip(),
        )
        account.set_password(password)
        account.save()
        link_client_account(account)
    return account


def authenticate_password(*, email: str, password: str) -> ClientAccount:
    """Mode A login: verify email + password (uniform error, no enumeration)."""
    email = normalize_client_email(email)
    try:
        account = ClientAccount.objects.get(email=email, is_active=True)
    except ClientAccount.DoesNotExist as exc:
        raise ClientAuthError("Неверная почта или пароль.") from exc
    if not account.check_password(password or ""):
        raise ClientAuthError("Неверная почта или пароль.")
    return account


def start_client_otp(request: HttpRequest, email: str) -> dict[str, str]:
    """Mode B step 1: email a fresh 6-digit code; return challenge id."""
    email = normalize_client_email(email)
    consume_otp_request_quota(
        request,
        cache_prefix=_OTP_REQ_PREFIX,
        limit=int(getattr(settings, "CLIENT_OTP_REQUEST_LIMIT", 20)),
        window=int(getattr(settings, "CLIENT_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    account, created = ClientAccount.objects.get_or_create(
        email=email,
        defaults={"auth_mode": ClientAuthMode.OTP_EMAIL},
    )
    if not account.is_active:
        raise ClientAuthError("Аккаунт недоступен. Обратитесь к менеджеру.")
    if created:
        link_client_account(account)
    code = generate_otp_code()
    challenge_id = secrets.token_urlsafe(24)
    payload = {
        "account_id": account.pk,
        "code_hash": hash_otp_code(code),
        "attempts": 0,
        "sent_at": time.time(),
        "resend_after": time.time() + otp_resend_cooldown_seconds("CLIENT_OTP"),
    }
    cache.set(_otp_key(challenge_id), payload, timeout=otp_ttl_seconds("CLIENT_OTP"))
    _send_client_otp_email(email=email, code=code)
    return {"challenge_id": challenge_id, "email_masked": mask_email(email)}


def verify_client_otp(*, challenge_id: str, code: str) -> ClientAccount:
    """Mode B step 2: validate code → account (marks email verified)."""
    payload = cache.get(_otp_key(challenge_id))
    if not payload:
        raise ClientAuthError("Код истёк — запросите новый.")
    if payload["attempts"] >= otp_max_attempts("CLIENT_OTP"):
        cache.delete(_otp_key(challenge_id))
        raise ClientAuthError("Превышено число попыток — запросите новый код.")
    if hash_otp_code((code or "").strip()) != payload["code_hash"]:
        payload["attempts"] += 1
        cache.set(_otp_key(challenge_id), payload, timeout=otp_ttl_seconds("CLIENT_OTP"))
        raise ClientAuthError("Неверный код.")
    cache.delete(_otp_key(challenge_id))
    try:
        account = ClientAccount.objects.get(pk=payload["account_id"], is_active=True)
    except ClientAccount.DoesNotExist as exc:
        raise ClientAuthError("Аккаунт недоступен.") from exc
    if account.email_verified_at is None:
        from django.utils import timezone

        account.email_verified_at = timezone.now()
        account.save(update_fields=["email_verified_at", "updated_at"])
    return account


def resend_client_otp(request: HttpRequest, challenge_id: str) -> dict[str, str]:
    """Re-send the OTP email honouring the resend cooldown."""
    payload = cache.get(_otp_key(challenge_id))
    if not payload:
        raise ClientAuthError("Код истёк — запросите новый.")
    now = time.time()
    if now < payload["resend_after"]:
        raise ClientAuthError("Подождите перед повторной отправкой.")
    account = ClientAccount.objects.get(pk=payload["account_id"], is_active=True)
    consume_otp_request_quota(
        request,
        cache_prefix=_OTP_REQ_PREFIX,
        limit=int(getattr(settings, "CLIENT_OTP_REQUEST_LIMIT", 20)),
        window=int(getattr(settings, "CLIENT_OTP_REQUEST_WINDOW_SECONDS", 3600)),
    )
    code = generate_otp_code()
    payload["code_hash"] = hash_otp_code(code)
    payload["attempts"] = 0
    payload["sent_at"] = now
    payload["resend_after"] = now + otp_resend_cooldown_seconds("CLIENT_OTP")
    cache.set(_otp_key(challenge_id), payload, timeout=otp_ttl_seconds("CLIENT_OTP"))
    _send_client_otp_email(email=account.email, code=code)
    return {"challenge_id": challenge_id, "email_masked": mask_email(account.email)}


def _otp_key(challenge_id: str) -> str:
    return f"{_OTP_CHALLENGE_PREFIX}{challenge_id}"


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
