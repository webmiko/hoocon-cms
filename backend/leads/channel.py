"""How a manager should read a lead on the board.

A public form is «Форма сайта». A call the PBX attached to the lead is
«Звонок принят» when someone talked and «Звонок пропущен» otherwise.
The latest call wins. A stub card (``@call.invalid``) is not a site form:
the manager still has to fill the client and write a note.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from django.utils import timezone

from crm.call_cards import STUB_EMAIL_SUFFIX, _phone_label
from crm.models import Call, Client
from crm.telephony import normalize_phone_digits
from leads.models import Lead

CallOutcome = Literal["answered", "missed"]

SITE_LABEL = "Форма сайта"
CALL_ANSWERED_LABEL = "Звонок принят"
CALL_MISSED_LABEL = "Звонок пропущен"
STUB_CARD_HINT = "Заведите карточку клиента и заметку о звонке"
STUB_CARD_DETAIL = (
    "Это звонок, а не форма с сайта. Карточка клиента ещё не заведена: "
    "откройте её, укажите имя, компанию и почту и добавьте заметку о звонке в ленте."
)


@dataclass(frozen=True)
class LeadChannel:
    """Board chips for one lead."""

    site: bool
    call: CallOutcome | None
    stub: bool


def is_call_stub_email(email: str) -> bool:
    """True for the placeholder address opened from an unknown number."""
    return (email or "").casefold().endswith(STUB_EMAIL_SUFFIX)


def call_was_answered(call: Call) -> bool:
    """A talk longer than zero seconds, or a connect timestamp, counts as answered."""
    return call.talk_duration > 0 or call.connected_at is not None


def latest_lead_call(lead: object) -> Call | None:
    """Newest call on this lead. Uses a prefetch when the changelist loaded one."""
    if not getattr(lead, "pk", None):
        return None
    prefetched = getattr(lead, "_prefetched_objects_cache", None)
    calls = getattr(lead, "calls", None)
    if calls is None:
        return None
    if isinstance(prefetched, dict) and "calls" in prefetched:
        rows = list(calls.all())
        return rows[0] if rows else None
    from django.db.models import F

    return calls.order_by(F("started_at").desc(nulls_last=True), "-pk").first()


def phone_label_for_lead(lead: object) -> str:
    """Formatted caller number. The stub email is ``<digits>@call.invalid``."""
    digits = normalize_phone_digits(getattr(lead, "phone", "") or "")
    if len(digits) < 10:
        email = getattr(lead, "email", "") or ""
        digits = normalize_phone_digits(email.split("@", 1)[0])
    if len(digits) >= 10:
        return _phone_label(digits)
    return "без номера"


def name_is_call_placeholder(name: str, phone_label: str) -> bool:
    """True while the manager has not typed a real client name."""
    stripped = (name or "").strip()
    if not stripped or stripped == phone_label:
        return True
    compact = "".join(ch for ch in stripped if ch.isdigit())
    phone_digits = "".join(ch for ch in phone_label if ch.isdigit())
    if compact and phone_digits and compact == phone_digits:
        return True
    return stripped.startswith(f"{CALL_ANSWERED_LABEL} ·") or stripped.startswith(f"{CALL_MISSED_LABEL} ·")


def format_temporary_call_name(*, phone_label: str, answered: bool, when: datetime | None) -> str:
    """Unique stand-in until the client card has a real name.

    Phone and time keep two calls from looking like the same consultation.
    """
    outcome = CALL_ANSWERED_LABEL if answered else CALL_MISSED_LABEL
    if when is None:
        return f"{outcome} · {phone_label}"
    local = timezone.localtime(when)
    return f"{outcome} · {phone_label} · {local:%d.%m %H:%M}"


def temporary_call_name(lead: object) -> str:
    """Board title for a stub whose stored name is still a phone or a previous stand-in."""
    phone_label = phone_label_for_lead(lead)
    call = latest_lead_call(lead)
    if call is not None:
        when = call.started_at or call.created_at
        answered = call_was_answered(call)
    else:
        when = getattr(lead, "created_at", None)
        answered = False
    return format_temporary_call_name(phone_label=phone_label, answered=answered, when=when)


def remember_temporary_call_name(call: Call) -> None:
    """Write the stand-in onto the stub card and its lead. A real name stays."""
    client = call.client
    if not isinstance(client, Client) or not is_call_stub_email(client.email):
        return
    phone_label = phone_label_for_lead(client)
    fresh = format_temporary_call_name(
        phone_label=phone_label,
        answered=call_was_answered(call),
        when=call.started_at or call.finished_at or call.created_at,
    )
    if name_is_call_placeholder(client.name, phone_label) and client.name != fresh:
        client.name = fresh
        client.save(update_fields=["name", "updated_at"])
    lead = call.lead
    if isinstance(lead, Lead) and name_is_call_placeholder(lead.name, phone_label) and lead.name != fresh:
        lead.name = fresh
        lead.save(update_fields=["name", "updated_at"])


def lead_channel(lead: object) -> LeadChannel:
    """Site form, call outcome, and whether the client card is still a stub.

    A telephony stub is never labeled as a site form. When several calls
    share the lead, only the latest one decides принят / пропущен.
    """
    email = getattr(lead, "email", "") or ""
    stub = is_call_stub_email(email)
    call = latest_lead_call(lead)
    outcome: CallOutcome | None
    if call is not None:
        outcome = "answered" if call_was_answered(call) else "missed"
    elif stub:
        outcome = "missed"
    else:
        outcome = None
    return LeadChannel(site=not stub, call=outcome, stub=stub)
