"""Top panel of a contact (person) card: who, what next, what already happened.

The contact page carries nine tables (leads, activities, calls, letters,
chats, offers, orders, claims, documents). The panel puts the one thing a
manager needs first above them: the actions and one history of this person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse
from django.utils import timezone

from crm.call_cards import STUB_EMAIL_SUFFIX
from crm.company_card import _next_step, feed_for_people
from crm.models import Client

FEED_SIZE = 12


@dataclass
class PersonCard:
    """Everything the panel template needs."""

    name: str
    chips: tuple[str, ...] = ()
    next_step: dict[str, Any] = field(default_factory=dict)
    call_url: str = ""
    write_url: str = ""
    quote_url: str = ""
    company_url: str = ""
    company_name: str = ""
    result_url: str = ""
    can_note: bool = False
    note_url: str = ""
    feed: list[Any] = field(default_factory=list)
    stub_mail: bool = False
    sections: list[dict[str, Any]] = field(default_factory=list)
    import_spec_url: str = ""
    history_url: str = ""


def build_person_card(person: Client, user: Any) -> PersonCard:
    """Panel for one contact as seen by ``user``."""
    real_mail = bool(person.email) and not person.email.endswith(STUB_EMAIL_SUFFIX)
    company: Any = person.company_ref if person.company_ref_id else None
    chips = tuple(
        chip
        for chip in (
            company.name if company is not None else (person.company or ""),
            person.email if real_mail else "",
            person.phone,
        )
        if chip
    )
    sections = _sections(person, user)
    card = PersonCard(
        sections=sections,
        name=person.name or person.email,
        chips=chips,
        next_step=_next_step(person, timezone.now()),
        stub_mail=not real_mail,
        can_note=user.has_perm("crm.add_activity"),
        note_url=reverse("crm-workspace-person-note", args=[person.pk]),
        feed=feed_for_people([person.pk], user, limit=FEED_SIZE),
    )
    if person.phone and user.has_perm("crm.view_call"):
        card.call_url = reverse("admin:crm_client_call_client", args=[person.pk])
    if real_mail and user.has_perm("crm.add_emailmessage"):
        card.write_url = reverse("admin:crm_client_compose_email", args=[person.pk])
    if user.has_perm("crm.add_quote"):
        card.quote_url = reverse("admin:crm_quote_add") + f"?client={person.pk}"
    if user.has_perm("crm.change_client") and user.has_perm("leads.add_lead"):
        card.import_spec_url = reverse("admin:crm_client_import_spec", args=[person.pk])
    if user.has_perm("crm.view_client"):
        card.history_url = reverse("admin:crm_client_history", args=[person.pk])
    if company is not None and user.has_perm("crm.view_company"):
        card.company_url = reverse("admin:crm_company_change", args=[company.pk])
        card.company_name = company.name
        if person.phone and user.has_perm("crm.change_company"):
            card.result_url = card.company_url + "#hoocon-card-top"
    return card


def _sections(person: Client, user: Any) -> list[dict[str, Any]]:
    """Jump links to the card's tabs, with how many rows each holds."""
    from cabinet.models import Order
    from crm.models import Call, EmailMessage, Quote
    from crm.services import (
        scope_calls_for_manager,
        scope_emails_for_manager,
        scope_orders_for_manager,
        scope_quotes_for_manager,
    )

    spec: tuple[tuple[str, str, str, Any, Any], ...] = (
        ("emails", "Письма", "crm.view_emailmessage", scope_emails_for_manager, EmailMessage),
        ("orders", "Заказы", "cabinet.view_order", scope_orders_for_manager, Order),
        ("quotes", "КП", "crm.view_quote", scope_quotes_for_manager, Quote),
        ("calls", "Звонки", "crm.view_call", scope_calls_for_manager, Call),
    )
    sections: list[dict[str, Any]] = []
    for tab, label, perm, scope, model in spec:
        if not user.has_perm(perm):
            continue
        count = scope(model.objects.filter(client_id=person.pk), user).count()
        sections.append({"tab": tab, "label": label, "count": count})
    return sections
