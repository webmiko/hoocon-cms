"""Top panel of a lead page: what the client wants and what to do now.

A manager opens a lead right after taking it. The standard page is eight
blocks of fields with the actions at the bottom. This panel answers three
questions first: what did the client write, what is the next step, and what
did we already do with this client.

The next step follows the lead's real state, so the primary button is never
a guess: take it, reach the client, finish the offer, wait for the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse
from django.utils import timezone

from crm.company_card import feed_for_people
from crm.workspace import human_wait

FEED_SIZE = 8
MESSAGE_LIMIT = 700


@dataclass(frozen=True)
class Button:
    """An action on the panel. ``post`` buttons need a CSRF form."""

    label: str
    url: str
    post: bool = False
    primary: bool = False


@dataclass
class LeadCard:
    """Everything the panel template needs."""

    state: str
    headline: str
    hint: str = ""
    buttons: list[Button] = field(default_factory=list)
    chips: tuple[str, ...] = ()
    message: str = ""
    items: list[str] = field(default_factory=list)
    waiting: str = ""
    owner: str = ""
    client_url: str = ""
    result_url: str = ""
    feed: list[Any] = field(default_factory=list)


def _stub(email: str) -> bool:
    from crm.call_cards import STUB_EMAIL_SUFFIX

    return not email or email.endswith(STUB_EMAIL_SUFFIX)


def _open_quote(lead: Any, user: Any) -> Any | None:
    from crm.models import Quote, QuoteStatus
    from crm.services import scope_quotes_for_manager

    quotes = scope_quotes_for_manager(
        Quote.objects.filter(lead=lead, status__in=(QuoteStatus.DRAFT, QuoteStatus.SENT)),
        user,
    )
    return quotes.order_by("-created_at").first()


def _tel(phone: str) -> str:
    from crm.telephony import normalize_phone_digits

    digits = normalize_phone_digits(phone or "")
    return f"+{digits}" if 10 <= len(digits) <= 15 else ""


def _owner_name(user: Any) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def build_lead_card(lead: Any, user: Any) -> LeadCard:
    """Panel for one lead as seen by ``user``."""
    from leads.models import Lead

    can_change = user.has_perm("leads.change_lead")
    mine = lead.assignee_id == user.pk
    free = lead.assignee_id is None
    quote = _open_quote(lead, user)
    tel = _tel(lead.phone)
    writable = not _stub(lead.email or "")
    close = Button("Закрыть заявку", reverse("crm-workspace-close-lead", args=[lead.pk]), post=True)

    buttons: list[Button] = []
    if lead.status == Lead.LeadStatus.DONE:
        state = "done"
        headline = "Заявка закрыта"
        hint = "Работа по ней завершена. Результат смотрите в КП ниже или в истории клиента."
        if quote is not None:
            buttons.append(
                Button(f"Открыть {quote.number}", reverse("admin:crm_quote_change", args=[quote.pk]), primary=True)
            )
    elif free and lead.status == Lead.LeadStatus.NEW:
        state = "free"
        headline = "Новая заявка: возьмите её в работу"
        hint = "После этого заявка закрепится за вами, и коллеги её не увидят."
        if can_change:
            buttons.append(
                Button("Взять в работу", reverse("crm-workspace-take-lead", args=[lead.pk]), post=True, primary=True),
            )
    elif not (mine or free) and not user.is_superuser:
        state = "other"
        headline = f"Заявку ведёт {_owner_name(lead.assignee)}"
        hint = "Вы видите её, но менять её может только ответственный."
    elif quote is not None and quote.status == "draft":
        state = "draft_quote"
        headline = "КП подготовлено: проверьте и выдайте клиенту"
        hint = f"{quote.number} лежит в черновиках. На его странице нажмите «Выдать клиенту»."
        buttons.append(
            Button(f"Открыть {quote.number}", reverse("admin:crm_quote_change", args=[quote.pk]), primary=True)
        )
    elif quote is not None:
        state = "waiting"
        headline = "КП выдано: ждём ответа клиента"
        hint = f"{quote.number} ушло клиенту. Если ответа нет три дня, оно появится в «Мой день»."
        buttons.append(
            Button(f"Открыть {quote.number}", reverse("admin:crm_quote_change", args=[quote.pk]), primary=True)
        )
    else:
        state = "contact"
        headline = "Свяжитесь с клиентом и подготовьте КП"
        hint = "Позвоните или напишите, уточните позиции, затем создайте КП."
        if tel:
            buttons.append(Button("Позвонить", f"tel:{tel}", primary=True))
        if user.has_perm("crm.add_quote") and (lead.email or "").strip():
            buttons.append(
                Button(
                    "Создать КП",
                    reverse("admin:leads_lead_create_quote", args=[lead.pk]),
                    post=True,
                    primary=not tel,
                ),
            )
    if state in {"contact", "draft_quote", "waiting"} and writable:
        buttons.append(Button("Ответить клиенту", reverse("admin:leads_lead_compose_reply", args=[lead.pk])))
    if state in {"contact", "draft_quote", "waiting"} and can_change:
        buttons.append(close)

    client = lead.client if lead.client_id else None
    result_url = ""
    feed: list[Any] = []
    client_url = ""
    if client is not None:
        client_url = reverse("admin:crm_client_change", args=[client.pk])
        if client.company_ref_id and tel and user.has_perm("crm.change_company"):
            result_url = reverse("admin:crm_company_change", args=[client.company_ref_id]) + "#hoocon-card-top"
        feed = feed_for_people([client.pk], user, limit=FEED_SIZE)

    message = " ".join((lead.message or "").split())
    if len(message) > MESSAGE_LIMIT:
        message = message[: MESSAGE_LIMIT - 1].rstrip() + "…"
    items = [f"{item.sku_code} × {item.quantity}" for item in lead.items.all()[:12] if item.sku_code]
    chips = tuple(
        chip
        for chip in (
            lead.get_lead_type_display(),
            lead.get_status_display(),
            lead.company,
            lead.phone,
            lead.email if writable else "",
        )
        if chip
    )
    waiting = human_wait(timezone.now() - lead.created_at) if lead.status == Lead.LeadStatus.NEW else ""
    return LeadCard(
        state=state,
        headline=headline,
        hint=hint,
        buttons=buttons,
        chips=chips,
        message=message,
        items=items,
        waiting=waiting,
        owner=_owner_name(lead.assignee),
        client_url=client_url,
        result_url=result_url,
        feed=feed,
    )
