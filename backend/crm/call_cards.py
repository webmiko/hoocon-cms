"""Bind a phone call to a CRM card.

A known number attaches to the existing client (a real card wins over a
stub created from an earlier unknown call). Click-to-call remembers the
card the manager opened, so the webhook still lands there when UIS reports
a different number. A finished call from an unknown number opens one card
and one consultation lead for the manager who spoke — a repeat call reuses
that card and does not email the client.
"""

from __future__ import annotations

from typing import Any, cast

from django.core.cache import cache
from django.db import IntegrityError, transaction

from crm.models import Call, Client
from crm.telephony import normalize_phone_digits

STUB_EMAIL_SUFFIX = "@call.invalid"
_SESSION_TTL = 6 * 60 * 60


def _session_key(session_id: str) -> str:
    return f"crm:uis-call:{session_id}"


def remember_uis_session(session_id: int | str, *, client_id: int, manager_id: int | None) -> None:
    """Remember which card a click-to-call started, until the webhook arrives."""
    cache.set(
        _session_key(str(session_id)),
        {"client_id": client_id, "manager_id": manager_id},
        timeout=_SESSION_TTL,
    )


def client_for_phone(phone: str) -> Client | None:
    """Active card for this number. A real email wins over a call stub."""
    digits = normalize_phone_digits(phone)
    if len(digits) < 5:
        return None
    cards = Client.objects.filter(is_active=True, phone_digits=digits)
    real = cards.exclude(email__iendswith=STUB_EMAIL_SUFFIX).order_by("id").first()
    if real is not None:
        return real
    return cards.order_by("id").first()


def _company_number() -> str:
    from sitesettings.telephony import novosystem_settings

    _enabled, _token, virtual, _secret = novosystem_settings()
    return normalize_phone_digits(virtual)


def _phone_label(digits: str) -> str:
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return f"+{digits}"


def _ensure_stub(digits: str, manager: Any) -> Client:
    """One card per unknown number. No client email and no round-robin."""
    from leads.models import Lead
    from leads.services import assign_lead_to_user

    email = f"{digits}{STUB_EMAIL_SUFFIX}"
    staff = manager if getattr(manager, "is_staff", False) and getattr(manager, "is_active", False) else None
    with transaction.atomic():
        try:
            client, _created = Client.objects.get_or_create(
                email=email,
                defaults={
                    "name": _phone_label(digits),
                    "phone": digits,
                    "assignee": staff,
                },
            )
        except IntegrityError:
            client = Client.objects.get(email=email)
        if not client.leads.exists():
            lead = Lead.objects.create(
                lead_type=Lead.LeadType.CONSULTATION,
                name=client.name or _phone_label(digits),
                email=client.email,
                phone=client.phone,
                message="Звонок с номера, которого не было в CRM.",
                client=client,
                contact_verified=False,
                status=Lead.LeadStatus.NEW,
            )
            if staff is not None:
                assign_lead_to_user(lead, staff)
    return client


def _cached_client(session_id: str) -> tuple[Client | None, int | None]:
    if not session_id:
        return None, None
    payload = cache.get(_session_key(session_id))
    if not isinstance(payload, dict):
        return None, None
    manager_id = payload.get("manager_id")
    raw_client_id = payload.get("client_id")
    client = (
        Client.objects.filter(pk=raw_client_id, is_active=True).first() if isinstance(raw_client_id, int) else None
    )
    return client, manager_id if isinstance(manager_id, int) else None


def attach_call_client(
    call: Call,
    *,
    contact_digits: str,
    session_id: str = "",
    create: bool = False,
) -> None:
    """Fill ``call.client`` and ``call.lead`` in memory. The caller saves.

    ``create`` is True only when the call has finished: a ringing leg must
    not open a card that the caller then abandons.
    """
    from crm.telephony import _latest_open_lead

    if call.client_id is None:
        cached, manager_id = _cached_client(session_id)
        if cached is not None:
            call.client = cached
            if call.manager_id is None and manager_id is not None:
                call.manager_id = manager_id
    if call.client_id is None:
        call.client = client_for_phone(contact_digits)
    digits = normalize_phone_digits(contact_digits)
    if call.client_id is None and create and len(digits) >= 10 and digits != _company_number():
        call.client = _ensure_stub(digits, call.manager)
    if call.client_id and call.lead_id is None:
        call.lead = _latest_open_lead(cast(Client | None, call.client))
    if create and call.client_id:
        from leads.channel import remember_temporary_call_name

        remember_temporary_call_name(call)
