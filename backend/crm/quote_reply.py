"""Client reply to an issued quote, without a cabinet login.

The email carries one signed token. Opening it does not change the quote:
the client confirms on the page. «Согласовать» moves SENT → ACCEPTED once.
«Нужны правки» keeps the status and records the comment on the card.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core import signing
from django.db import transaction
from django.utils import timezone

from crm.models import Activity, ActivityType, Client, Quote, QuoteStatus
from leads.models import Lead

logger = logging.getLogger("hoocon.crm")

_SALT = "hoocon.quote-client-reply"
_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
_COMMENT_MAX = 2000


class QuoteReplyError(Exception):
    """Client-visible refusal. ``status`` is the HTTP code."""

    def __init__(self, message: str, *, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def sign_quote_token(quote_id: int) -> str:
    """Signed token for the public reply page. Not a secret in logs."""
    return signing.TimestampSigner(salt=_SALT).sign(str(quote_id))


def quote_reply_urls(quote_id: int) -> tuple[str, str]:
    """Absolute accept and revise links for the quote email."""
    token = sign_quote_token(quote_id)
    base = settings.SITE_URL.rstrip("/")
    accept = f"{base}/kp?{urlencode({'t': token, 'action': 'accept'})}"
    revise = f"{base}/kp?{urlencode({'t': token, 'action': 'revise'})}"
    return accept, revise


def _unsigned_id(token: str) -> int | None:
    try:
        raw = signing.TimestampSigner(salt=_SALT).unsign(token, max_age=_MAX_AGE_SECONDS)
    except (signing.SignatureExpired, signing.BadSignature):
        return None
    if not str(raw).isdigit():
        return None
    return int(raw)


def load_reply_quote(token: str) -> Quote | None:
    """Issued quote for a valid token. Drafts and junk tokens are None."""
    quote_id = _unsigned_id((token or "").strip())
    if quote_id is None:
        return None
    quote = (
        Quote.objects.select_related("client", "created_by", "lead")
        .filter(pk=quote_id)
        .exclude(status=QuoteStatus.DRAFT)
        .first()
    )
    return quote


def quote_is_expired(quote: Quote) -> bool:
    """True after the calendar day named in ``valid_until`` (local date)."""
    if quote.valid_until is None:
        return False
    return quote.valid_until < timezone.localdate()


def _quote_client(quote: Quote) -> Client:
    return cast(Client, quote.client)


def _quote_lead(quote: Quote) -> Lead | None:
    return cast(Lead | None, quote.lead)


def _quote_manager(quote: Quote) -> AbstractBaseUser | None:
    created = quote.created_by
    if created is not None:
        return cast(AbstractBaseUser, created)
    assignee = _quote_client(quote).assignee
    return cast(AbstractBaseUser, assignee) if assignee is not None else None


def reply_preview(quote: Quote) -> dict[str, Any]:
    """Fields the public page may show. No prices and no client email."""
    from crm.manager_signatures import manager_public_contact

    contact = manager_public_contact(_quote_manager(quote))
    expired = quote_is_expired(quote)
    return {
        "number": quote.number,
        "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        "status": quote.status,
        "status_label": quote.get_status_display(),
        "expired": expired,
        "can_accept": quote.status == QuoteStatus.SENT and not expired,
        "manager_name": contact["name"],
        "manager_phone": contact["phone"],
    }


def _notify_manager(quote: Quote, *, subject: str, body: str) -> None:
    """Queue one letter to the manager. SMTP stays off the client's request."""
    from crm.mail_links import staff_reply_to_email
    from crm.tasks import send_quote_reply_mail

    recipient = staff_reply_to_email(_quote_manager(quote))
    if not recipient:
        return
    try:
        send_quote_reply_mail.delay(subject, body, recipient)
    except Exception as exc:
        logger.exception(
            "quote_reply_notify_enqueue_failed quote_id=%s type=%s",
            quote.pk,
            type(exc).__name__,
        )


def accept_quote(token: str) -> dict[str, Any]:
    """Move a live SENT quote to ACCEPTED. A second call does not email again."""
    from crm.quote_ops import transition_quote

    quote = load_reply_quote(token)
    if quote is None:
        raise QuoteReplyError("Ссылка недействительна.", status=404)
    with transaction.atomic():
        quote = Quote.objects.select_for_update().get(pk=quote.pk)
        if quote.status == QuoteStatus.ACCEPTED:
            return reply_preview(quote)
        if quote.status != QuoteStatus.SENT:
            raise QuoteReplyError("Это предложение уже закрыто.", status=400)
        if quote_is_expired(quote):
            raise QuoteReplyError("Срок предложения истёк. Напишите менеджеру.", status=400)
        _result, error = transition_quote(quote, QuoteStatus.ACCEPTED, actor=quote.created_by)
        if error:
            raise QuoteReplyError("Это предложение уже закрыто.", status=400)
        Activity.objects.create(
            client=_quote_client(quote),
            lead=_quote_lead(quote),
            activity_type=ActivityType.NOTE,
            subject=f"{quote.number}: клиент согласовал",
            body="",
        )
    quote.refresh_from_db()
    _notify_manager(
        quote,
        subject=f"{quote.number}: клиент согласовал",
        body=f"Клиент согласовал {quote.number}. Статус КП — «Согласовано».",
    )
    return reply_preview(quote)


def revise_quote(token: str, comment: str) -> dict[str, Any]:
    """Record a change request. The quote status stays as it is."""
    text = (comment or "").strip()
    if not text:
        raise QuoteReplyError("Напишите, что поправить.", status=400)
    if len(text) > _COMMENT_MAX:
        raise QuoteReplyError("Комментарий слишком длинный.", status=400)
    quote = load_reply_quote(token)
    if quote is None:
        raise QuoteReplyError("Ссылка недействительна.", status=404)
    if quote.status not in (QuoteStatus.SENT, QuoteStatus.ACCEPTED):
        raise QuoteReplyError("Это предложение уже закрыто.", status=400)
    Activity.objects.create(
        client=_quote_client(quote),
        lead=_quote_lead(quote),
        activity_type=ActivityType.NOTE,
        subject=f"{quote.number}: клиент просит правки",
        body=text,
    )
    _notify_manager(
        quote,
        subject=f"{quote.number}: клиент просит правки",
        body=f"Клиент просит поправить {quote.number}:\n\n{text}",
    )
    return reply_preview(quote)
