"""Top panel of the company card: what to do next and what happened so far.

A manager opens a firm to answer two questions: «what is the next step with
them» and «what did we already do». The standard form answers neither: it is
a list of fields, and the history is split over five tabs.

This module builds the answer once: one action bar and one chronological
feed of notes, calls, letters and offers. Every source goes through the same
scoping helper the lists use, so the feed never shows more than the manager
could open elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.urls import reverse
from django.utils import timezone

from crm.call_cards import STUB_EMAIL_SUFFIX
from crm.phones import split_phone_numbers
from crm.telephony import normalize_phone_digits
from crm.workspace import human_wait

FEED_LIMIT = 25
# Quick «next step» buttons: label → days from now.
NEXT_STEP_CHOICES: tuple[tuple[str, int], ...] = (
    ("Завтра", 1),
    ("Через 3 дня", 3),
    ("Через неделю", 7),
    ("Через 2 недели", 14),
)
# A new next step is set for the working morning, not for the moment of the click.
NEXT_STEP_HOUR = 10


@dataclass(frozen=True)
class FeedItem:
    """One line of the company feed."""

    when: datetime
    kind: str
    icon: str
    label: str
    title: str
    text: str = ""
    who: str = ""
    url: str = ""

    @property
    def ago(self) -> str:
        return human_wait(timezone.now() - self.when)


def next_step_target(days: int, *, now: datetime | None = None) -> datetime:
    """Local 10:00 of the day ``days`` ahead."""
    base = timezone.localtime(now or timezone.now()) + timedelta(days=days)
    return base.replace(hour=NEXT_STEP_HOUR, minute=0, second=0, microsecond=0)


def primary_person(company: Any, user: Any) -> Any | None:
    """The person a letter, an offer or a note goes to, among those ``user`` may work with.

    A free firm is open to every manager, but its people may belong to a
    colleague. A note on such a person would unlock their whole card for the
    author, so only people inside the manager's scope are candidates there.
    On the manager's own firm the people nobody has claimed yet are theirs
    too: the firm is theirs, and without this the panel would go silent.
    Prefers a real mailbox over the stub address a call creates, then the
    oldest card.
    """
    from django.db.models import Q

    from crm.services import scope_clients_for_manager

    people_qs = company.clients.filter(is_active=True)
    visible = scope_clients_for_manager(people_qs, user)
    if company.assignee_id is not None and company.assignee_id == getattr(user, "pk", None):
        visible = people_qs.filter(Q(pk__in=visible.values("pk")) | Q(assignee__isnull=True))
    people = list(visible.order_by("pk"))
    for person in people:
        if person.email and not person.email.endswith(STUB_EMAIL_SUFFIX):
            return person
    return people[0] if people else None


def build_company_card(company: Any, user: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Everything the panel above the company form needs."""
    now = now or timezone.now()
    person = primary_person(company, user)
    return {
        "next_step": _next_step(company, now),
        "next_step_choices": NEXT_STEP_CHOICES,
        "actions": _actions(company, person, user),
        "person": person,
        "feed": _feed(company, user),
        "can_edit": user.has_perm("crm.change_company"),
        "can_note": user.has_perm("crm.add_activity") and person is not None,
        "next_step_url": reverse("crm-workspace-company-next-step", args=[company.pk]),
        "note_url": reverse("crm-workspace-company-note", args=[company.pk]),
        "can_call_result": user.has_perm("crm.change_company") and user.has_perm("crm.add_activity"),
        "call_result_url": reverse("crm-workspace-company-call-result", args=[company.pk]),
        "outcomes": _outcomes(),
    }


def _outcomes() -> tuple[Any, ...]:
    from crm.call_outcome import OUTCOMES

    return OUTCOMES


def _next_step(company: Any, now: datetime) -> dict[str, Any]:
    due = company.next_contact_at
    if due is None:
        return {
            "state": "none",
            "text": "Следующий шаг не назначен",
            "hint": "Без даты клиент не попадёт в «Мой день». Выберите, когда вернуться к нему.",
            "due": None,
        }
    local = timezone.localtime(due)
    stamp = local.strftime("%d.%m в %H:%M")
    if due < now:
        return {
            "state": "overdue",
            "text": f"Просрочено: {human_wait(now - due)}",
            "hint": f"Надо было вернуться {stamp}.",
            "due": due,
        }
    return {"state": "ok", "text": f"Вернуться {stamp}", "hint": "", "due": due}


def _tel(company: Any, person: Any) -> str:
    candidates: list[str] = []
    candidates.extend(phone.number for phone in company.phones.all())
    candidates.extend(split_phone_numbers(company.phone or ""))
    if person is not None:
        candidates.extend(split_phone_numbers(person.phone or ""))
    for number in candidates:
        digits = normalize_phone_digits(number)
        if 10 <= len(digits) <= 15:
            return f"+{digits}"
    return ""


def _actions(company: Any, person: Any, user: Any) -> dict[str, str]:
    """Links for the action bar. An empty string hides the button."""
    links = {"call": "", "write": "", "quote": "", "person": ""}
    if user.has_perm("crm.view_call") or user.has_perm("crm.change_company"):
        links["call"] = _tel(company, person)
    if person is None:
        return links
    links["person"] = reverse("admin:crm_client_change", args=[person.pk])
    real_mail = bool(person.email) and not person.email.endswith(STUB_EMAIL_SUFFIX)
    if real_mail and user.has_perm("crm.add_emailmessage"):
        links["write"] = reverse("admin:crm_client_compose_email", args=[person.pk])
    if user.has_perm("crm.add_quote"):
        links["quote"] = reverse("admin:crm_quote_add") + f"?client={person.pk}"
    return links


def _feed(company: Any, user: Any) -> list[FeedItem]:
    return feed_for_people(list(company.clients.values_list("pk", flat=True)), user)


def feed_for_people(people: list[int], user: Any, *, limit: int = FEED_LIMIT) -> list[FeedItem]:
    """Notes, calls, letters and offers of these contacts, newest first.

    Shared by the company card and the lead page. Each source is scoped for
    the manager, so the feed never shows more than the lists would.
    """
    from crm.models import Activity, Call, EmailMessage, Quote
    from crm.services import (
        scope_activities_for_manager,
        scope_calls_for_manager,
        scope_emails_for_manager,
        scope_quotes_for_manager,
    )

    if not people:
        return []
    items: list[FeedItem] = []

    if user.has_perm("crm.view_activity"):
        activity_rows = scope_activities_for_manager(Activity.objects.filter(client_id__in=people), user)
        for activity in activity_rows.select_related("author", "client")[:limit]:
            items.append(
                FeedItem(
                    when=activity.created_at,
                    kind="note",
                    icon="edit_note",
                    label=activity.get_activity_type_display(),
                    title=activity.subject or activity.get_activity_type_display(),
                    text=_clip(activity.body),
                    who=_person(activity.author),
                ),
            )
    if user.has_perm("crm.view_call"):
        call_rows = scope_calls_for_manager(Call.objects.filter(client_id__in=people), user)
        for call in call_rows[:limit]:
            talk = call.talk_duration or 0
            items.append(
                FeedItem(
                    when=call.started_at or call.created_at,
                    kind="call",
                    icon="call_received" if call.direction == "inbound" else "call_made",
                    label=call.get_direction_display(),
                    title=f"Звонок, {talk // 60}:{talk % 60:02d}" if talk else "Звонок без разговора",
                    url=reverse("admin:crm_call_change", args=[call.pk]),
                ),
            )
    if user.has_perm("crm.view_emailmessage"):
        mail_rows = scope_emails_for_manager(EmailMessage.objects.filter(client_id__in=people), user)
        for mail in mail_rows[:limit]:
            inbound = mail.direction == "inbound"
            items.append(
                FeedItem(
                    when=mail.sent_at or mail.created_at,
                    kind="mail",
                    icon="mark_email_unread" if inbound else "send",
                    label="Письмо от клиента" if inbound else "Письмо клиенту",
                    title=mail.subject,
                    text=_clip(mail.body),
                    url=reverse("admin:crm_emailmessage_change", args=[mail.pk]),
                ),
            )
    if user.has_perm("crm.view_quote"):
        quote_rows = scope_quotes_for_manager(Quote.objects.filter(client_id__in=people), user)
        for quote in quote_rows.select_related("created_by")[:limit]:
            items.append(
                FeedItem(
                    when=quote.sent_at or quote.created_at,
                    kind="quote",
                    icon="request_quote",
                    label=f"КП · {quote.get_status_display()}",
                    title=quote.number or f"КП-{quote.pk}",
                    who=_person(quote.created_by),
                    url=reverse("admin:crm_quote_change", args=[quote.pk]),
                ),
            )
    if user.has_perm("cabinet.view_order"):
        from cabinet.models import Order
        from crm.services import scope_orders_for_manager

        order_rows = scope_orders_for_manager(Order.objects.filter(client_id__in=people), user)
        for order in order_rows[:limit]:
            items.append(
                FeedItem(
                    when=order.created_at,
                    kind="order",
                    icon="orders",
                    label=f"Заказ · {order.get_status_display()}",
                    title=order.number,
                    url=reverse("admin:cabinet_order_change", args=[order.pk]),
                ),
            )
    items.sort(key=lambda item: item.when, reverse=True)
    return items[:limit]


def _person(user: Any) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def _clip(text: str, limit: int = 160) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"
