"""Quote document lifecycle: PDF → ClientDocument + client notification.

При переводе КП в «Выдано» (``QuoteStatus.SENT``) генерируется PDF,
складывается в private media как ``ClientDocument(kind=quote_pdf)`` —
клиент видит его в кабинете и на карточке клиента. Письмо-уведомление
идёт через обычный CRM-контур (``create_outbound_email``), т.е. с личного
ящика менеджера, когда он настроен.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

from crm.models import Client, ClientDocument, DocumentKind, Quote
from leads.models import Lead

if TYPE_CHECKING:
    from crm.models import EmailMessage

logger = logging.getLogger(__name__)

QUOTE_ISSUED_SUBJECT_MARKER = "коммерческое предложение Hoocon"


def ensure_quote_pdf_document(quote: Quote) -> ClientDocument:
    """Create (or refresh) the ``quote_pdf`` ClientDocument for a quote.

    Idempotent per quote: a second call replaces the file of the existing
    document instead of spawning duplicates.
    """
    from crm.quote_pdf import render_quote_pdf

    client = cast(Client, quote.client)
    doc, _ = ClientDocument.objects.get_or_create(
        quote=quote,
        kind=DocumentKind.QUOTE_PDF,
        defaults={"client": client, "title": f"{quote.number}.pdf"},
    )
    if doc.client_id != quote.client_id:
        doc.client = client
    doc.title = f"{quote.number}.pdf"
    buf = render_quote_pdf(quote)
    doc.file.save(doc.title, ContentFile(buf.getvalue()), save=False)
    doc.save()
    logger.info("quote_pdf_document quote_id=%s doc_id=%s", quote.pk, doc.pk)
    return doc


def _quote_email_signature(manager: Any) -> dict[str, str]:
    """Signature block for the quote letter (same sources as lead confirmation)."""
    from crm.manager_signatures import manager_public_contact, manager_signature_contacts

    contact = manager_public_contact(manager)
    email = contact["email"]
    sig = manager_signature_contacts(email) if email else None
    company = (sig.get("company") if sig else None) or 'ООО "ХОГОН"'
    phone = contact["phone"]
    name = contact["name"] or "Команда продаж Hoocon"
    return {
        "name": name,
        "company": company,
        "phone": phone,
        "tel_href": "+" + re.sub(r"\D", "", phone) if phone else "",
        "email": email,
    }


def _quote_email_manager_block(manager: Any) -> dict[str, str]:
    """Manager contacts shown in the «Ваш менеджер» callout."""
    from crm.manager_signatures import manager_public_contact

    contact = manager_public_contact(manager)
    phone = contact["phone"]
    return {
        "name": contact["name"],
        "phone": phone,
        "email": contact["email"],
        "tel_href": "+" + re.sub(r"\D", "", phone) if phone else "",
    }


def render_quote_issued_email(
    quote: Quote,
    *,
    author: AbstractBaseUser | None = None,
) -> tuple[str, str, str]:
    """Subject, plain text, and HTML bodies for the issued-quote client email."""
    from crm.quote_reply import quote_reply_urls

    client = cast(Client, quote.client)
    manager = author or quote.created_by or client.assignee
    accept_url, revise_url = quote_reply_urls(quote.pk)
    site_url = getattr(settings, "SITE_URL", "").rstrip("/") or "https://hoocon.ru"
    valid_until_label = quote.valid_until.strftime("%d.%m.%Y") if quote.valid_until else ""
    context = {
        "site_url": site_url,
        "brand_name": "Hoocon",
        "quote_number": quote.number,
        "client_name": (client.name or "").strip(),
        "valid_until_label": valid_until_label,
        "manager": _quote_email_manager_block(manager),
        "accept_url": accept_url,
        "revise_url": revise_url,
        "signature": _quote_email_signature(manager),
    }
    subject = f"{quote.number} — {QUOTE_ISSUED_SUBJECT_MARKER}"
    text_body = render_to_string("crm/email/quote_issued.txt", context).strip()
    html_body = render_to_string("crm/email/quote_issued.html", context).strip()
    return subject, text_body, html_body


def notify_quote_issued(
    quote: Quote,
    *,
    author: AbstractBaseUser | None = None,
    send_now: bool = True,
    document: ClientDocument | None = None,
) -> EmailMessage:
    """Queue the «КП выдано» email to the client with the PDF attached."""
    from crm.manager_signatures import manager_public_contact
    from crm.services import create_outbound_email

    client = cast(Client, quote.client)
    lead = cast(Lead | None, quote.lead)
    attachments = None
    if document is not None and document.file:
        with document.file.open("rb") as fh:
            pdf_bytes = fh.read()
        attachments = [(document.title or f"{quote.number}.pdf", "application/pdf", pdf_bytes)]
    manager = author or quote.created_by or client.assignee
    contact = manager_public_contact(manager)
    subject, _text_body, html_body = render_quote_issued_email(quote, author=author)
    return create_outbound_email(
        client=client,
        subject=subject,
        body=html_body,
        lead=lead,
        quote=quote,
        author=author,
        send_now=send_now,
        attachments=attachments,
        reply_to_email=contact["email"],
    )
