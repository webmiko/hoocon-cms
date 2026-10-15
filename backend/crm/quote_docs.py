"""Quote document lifecycle: PDF → ClientDocument + client notification.

При переводе КП в «Выдано» (``QuoteStatus.SENT``) генерируется PDF,
складывается в private media как ``ClientDocument(kind=quote_pdf)`` —
клиент видит его в кабинете и на карточке клиента. Письмо-уведомление
идёт через обычный CRM-контур (``create_outbound_email``), т.е. с личного
ящика менеджера, когда он настроен.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from django.contrib.auth.models import AbstractBaseUser
from django.core.files.base import ContentFile

from crm.models import Client, ClientDocument, DocumentKind, Quote
from leads.models import Lead

if TYPE_CHECKING:
    from crm.models import EmailMessage

logger = logging.getLogger(__name__)


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


def notify_quote_issued(
    quote: Quote,
    *,
    author: AbstractBaseUser | None = None,
    send_now: bool = True,
    document: ClientDocument | None = None,
) -> EmailMessage:
    """Queue the «КП выдано» email to the client with the PDF attached."""
    from crm.services import create_outbound_email

    client = cast(Client, quote.client)
    lead = cast(Lead | None, quote.lead)
    attachments = None
    if document is not None and document.file:
        with document.file.open("rb") as fh:
            pdf_bytes = fh.read()
        attachments = [(document.title or f"{quote.number}.pdf", "application/pdf", pdf_bytes)]
    from crm.manager_signatures import manager_public_contact
    from crm.quote_reply import quote_reply_urls

    manager = author or quote.created_by or client.assignee
    contact = manager_public_contact(manager)
    accept_url, revise_url = quote_reply_urls(quote.pk)
    lines = [
        "Здравствуйте!",
        "",
        f"Коммерческое предложение {quote.number} — PDF во вложении.",
    ]
    if quote.valid_until:
        lines.append(f"Действует до {quote.valid_until:%d.%m.%Y}.")
    if contact["name"] or contact["phone"] or contact["email"]:
        lines.extend(["", "Ваш менеджер:"])
        if contact["name"]:
            lines.append(contact["name"])
        if contact["phone"]:
            lines.append(f"Телефон: {contact['phone']}")
        if contact["email"]:
            lines.append(f"Почта: {contact['email']}")
    lines.extend(
        [
            "",
            f"Согласовать: {accept_url}",
            f"Нужны правки: {revise_url}",
            "",
            "Ссылки открываются без входа в кабинет.",
        ],
    )
    return create_outbound_email(
        client=client,
        subject=f"{quote.number} — коммерческое предложение Hoocon",
        body="\n".join(lines),
        lead=lead,
        author=author,
        send_now=send_now,
        attachments=attachments,
        reply_to_email=contact["email"],
    )
