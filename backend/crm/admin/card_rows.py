"""Fill a lead or order typed on the client card during a phone call."""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from cabinet.models import Order
from crm.models import Client
from leads.models import Lead


def fill_manual_lead(lead: Lead, client: Client, actor: Any) -> None:
    """Copy the card onto a lead the manager typed during a call.

    The site form notifies sales and the client. This row does not: the
    manager is already on the phone, and the contact is the card itself.
    """
    lead.name = (lead.name or "").strip() or (client.name or "").strip() or client.email
    lead.email = (lead.email or "").strip() or client.email
    lead.company = (lead.company or "").strip() or (client.company or "").strip()
    lead.contact_verified = True
    if lead.assignee_id is None and getattr(actor, "is_authenticated", False):
        lead.assignee = actor


def next_manual_order_number(client: Client) -> str:
    """``З-ГГММДД`` for a phone order, with a suffix if that number is taken."""
    base = f"З-{timezone.localdate():%y%m%d}"
    number = base
    suffix = 2
    while Order.objects.filter(client_id=client.pk, number=number).exists():
        number = f"{base}-{suffix}"
        suffix += 1
    return number
