"""CRM services: find/create Client from Lead, queue outbound email."""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction

from crm.models import (
    Activity,
    ActivityType,
    Client,
    EmailDirection,
    EmailMessage,
    EmailStatus,
)
from leads.models import Lead

logger = logging.getLogger("hoocon.crm")


def get_or_create_client_from_lead(lead: Lead) -> Client:
    """Find Client by email or create from Lead contact fields.

    Args:
        lead: saved Lead instance.

    Returns:
        Client linked (or to be linked) to this lead.
    """
    email = (lead.email or "").strip().lower()
    client = Client.objects.filter(email__iexact=email).first()
    if client is None:
        client = Client.objects.create(
            name=lead.name.strip() or email,
            email=email,
            phone=lead.phone or "",
            company=lead.company or "",
        )
        return client

    # Refresh sparse fields from newer lead if empty on client.
    updated = False
    if not client.phone and lead.phone:
        client.phone = lead.phone
        updated = True
    if not client.company and lead.company:
        client.company = lead.company
        updated = True
    if lead.name and client.name == client.email and lead.name.strip():
        client.name = lead.name.strip()
        updated = True
    if updated:
        client.save()
    return client


def link_lead_to_client(lead: Lead) -> Client:
    """Ensure Lead.client is set; create Client if needed.

    Args:
        lead: Lead to attach.

    Returns:
        The Client instance.
    """
    if lead.client_id:
        return lead.client  # type: ignore[return-value]
    client = get_or_create_client_from_lead(lead)
    Lead.objects.filter(pk=lead.pk).update(client_id=client.pk)
    lead.client_id = client.pk
    lead.client = client
    return client


def create_outbound_email(
    *,
    client: Client,
    subject: str,
    body: str,
    to_email: str | None = None,
    lead: Lead | None = None,
    author: AbstractBaseUser | None = None,
    send_now: bool = True,
) -> EmailMessage:
    """Create an outbound EmailMessage and optionally queue send.

    Args:
        client: CRM client.
        subject: email subject.
        body: plain-text body.
        to_email: override recipient (default client.email).
        lead: optional related Lead.
        author: staff User who composed the message.
        send_now: enqueue Celery send after commit.

    Returns:
        Created EmailMessage (status DRAFT or QUEUED).
    """
    from_addr = getattr(settings, "DEFAULT_FROM_EMAIL", "") or "webmaster@localhost"
    created_by = author if author is not None and author.is_authenticated else None
    msg = EmailMessage.objects.create(
        client=client,
        lead=lead,
        direction=EmailDirection.OUTBOUND,
        status=EmailStatus.QUEUED if send_now else EmailStatus.DRAFT,
        to_email=(to_email or client.email).strip(),
        from_email=from_addr,
        subject=subject.strip(),
        body=body.strip(),
        created_by=created_by,  # type: ignore[misc]
    )
    Activity.objects.create(
        client=client,
        lead=lead,
        activity_type=ActivityType.EMAIL,
        subject=msg.subject,
        body=msg.body[:2000],
        author=created_by,  # type: ignore[misc]
    )
    if send_now:
        from crm.tasks import send_crm_email

        email_id = msg.pk

        def _enqueue() -> None:
            send_crm_email.delay(email_id)

        transaction.on_commit(_enqueue)
    return msg
