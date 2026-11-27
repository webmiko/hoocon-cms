"""«Мой день» — one queue of things a sales manager should do right now.

The admin is organised by database tables. A manager thinks in tasks:
«who is waiting for me», «whom do I call back», «whose offer is silent».
This module answers that single question and nothing else.

Every row has the same shape: what happened, to whom, how long it has
been waiting, and one main button. Rows are ordered by how much money
waits on them, so the first row is always the one to start with.

Scoping reuses the same helpers as the lists, so a manager never sees a
colleague's client here that they could not open from the menu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

from django.urls import reverse
from django.utils import timezone

from crm.today import build_today_board

# A sent offer with no reply for this long deserves a nudge.
QUOTE_SILENCE_DAYS = 3
# Companies whose «next contact» slipped further than this are archive, not work.
COMPANY_OVERDUE_DAYS = 14
# New leads and chats older than this are backlog, not «now»: they must not
# take the «start here» slot, but they are still counted so nobody forgets.
STALE_DAYS = 14
# One section never shows more rows than this; the rest is a link to the list.
SECTION_LIMIT = 6


@dataclass(frozen=True)
class Action:
    """A button on a queue row."""

    label: str
    url: str
    post: bool = False
    # ``tel:`` links must not go through the router or the CSRF form.
    external: bool = False
    # Asked before a destructive POST; empty means no question.
    confirm: str = ""


@dataclass(frozen=True)
class Row:
    """One thing waiting for the manager."""

    title: str
    subtitle: str
    waiting: str
    primary: Action
    secondary: Action | None = None
    # «Завершить»: the thing was handled outside the CRM, just remove it from the queue.
    finish: Action | None = None
    urgent: bool = False
    # Cards only: what the client wrote and how to reach them.
    text: str = ""
    chips: tuple[str, ...] = ()


@dataclass
class Section:
    """A group of rows answering one question."""

    key: str
    title: str
    hint: str
    rows: list[Row] = field(default_factory=list)
    total: int = 0
    stale: int = 0
    stale_url: str = ""
    all_url: str = ""
    all_label: str = "Показать все"
    # «cards» for entry points where the manager reads what the client wrote,
    # «rows» for follow-ups where a name and a reason are enough.
    layout: str = "rows"

    @property
    def more(self) -> int:
        return max(0, self.total - len(self.rows))


def _finish(label: str, url_name: str, pk: int, confirm: str) -> Action:
    return Action(label, reverse(url_name, args=[pk]), post=True, confirm=confirm)


_FINISH_LEAD_CONFIRM = (
    "Завершить заявку? Она закроется и пропадёт из очереди. Нажимайте, если уже обработали её вне CRM, например в 1С."
)


def human_wait(delta: timedelta) -> str:
    """«12 мин», «3 ч», «2 дн.» — how long something has been waiting."""
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч"
    return f"{hours // 24} дн."


def build_workspace(user: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Everything the «Мой день» page needs for one manager.

    Returns:
        ``first`` — the row to start with (or None), ``sections`` — non-empty
        groups in priority order, ``funnel`` — the four-step client path with
        counters, ``total`` — rows waiting in all groups.
    """
    now = now or timezone.now()
    candidates = [
        _new_leads(user, now),
        _unread_chats(user, now),
        _planned_calls(user),
        _silent_quotes(user, now),
        _company_follow_ups(user, now),
        _leads_in_work(user, now),
    ]
    sections: list[Section] = [item for item in candidates if item is not None and (item.total or item.stale)]
    first = next((section.rows[0] for section in sections if section.rows), None)
    return {
        "first": first,
        "sections": sections,
        "total": sum(section.total for section in sections),
        "stale": sum(section.stale for section in sections),
        "funnel": _funnel(user, now),
    }


def _new_leads(user: Any, now: datetime) -> Section | None:
    if not user.has_perm("leads.view_lead"):
        return None
    from leads.models import Lead
    from leads.services import scope_leads_for_manager

    scoped = scope_leads_for_manager(Lead.objects.filter(status=Lead.LeadStatus.NEW), user)
    border = now - timedelta(days=STALE_DAYS)
    queryset = scoped.filter(created_at__gte=border).order_by("created_at")
    total = queryset.count()
    stale = scoped.filter(created_at__lt=border).count()
    can_take = user.has_perm("leads.change_lead")
    rows = []
    for lead in queryset.select_related("assignee")[:SECTION_LIMIT]:
        open_url = reverse("admin:leads_lead_change", args=[lead.pk])
        who = lead.name
        if lead.company:
            who = f"{lead.name}, {lead.company}"
        take = Action("Взять в работу", reverse("crm-workspace-take-lead", args=[lead.pk]), post=True)
        rows.append(
            Row(
                title=who,
                subtitle=f"{lead.get_lead_type_display()} · {_clip(lead.message)}",
                text=_clip(lead.message, 220),
                chips=tuple(chip for chip in (lead.get_lead_type_display(), lead.phone, lead.email) if chip),
                waiting=human_wait(now - lead.created_at),
                primary=take if can_take and lead.assignee_id is None else Action("Открыть", open_url),
                secondary=Action("Открыть", open_url) if can_take and lead.assignee_id is None else None,
                finish=_finish("Завершить", "crm-workspace-finish-lead", lead.pk, _FINISH_LEAD_CONFIRM)
                if can_take
                else None,
                urgent=now - lead.created_at > timedelta(hours=1),
            ),
        )
    return Section(
        key="new-leads",
        layout="cards",
        title="Новые заявки",
        hint="Клиент ждёт ответа. Чем раньше возьмёте — тем выше шанс продажи.",
        rows=rows,
        total=total,
        stale=stale,
        stale_url=reverse("admin:leads_lead_changelist") + "?status__exact=new",
        all_url=reverse("admin:leads_lead_changelist") + "?status__exact=new",
    )


def _unread_chats(user: Any, now: datetime) -> Section | None:
    if not user.has_perm("supportchat.view_conversation"):
        return None
    from django.db.models import Q

    from accounts.roles import staff_sees_all_leads
    from supportchat.models import Conversation, ConversationStatus, MessageDirection

    queryset = Conversation.objects.filter(status=ConversationStatus.OPEN, staff_unread_count__gt=0)
    if not staff_sees_all_leads(user):
        queryset = queryset.filter(Q(assignee__isnull=True) | Q(assignee=user))
    border = now - timedelta(days=STALE_DAYS)
    stale = queryset.filter(last_message_at__lt=border).count()
    queryset = queryset.filter(last_message_at__gte=border).order_by("last_message_at")
    total = queryset.count()
    rows = []
    for chat in queryset[:SECTION_LIMIT]:
        since = chat.last_message_at or now
        count = chat.staff_unread_count
        last = chat.messages.filter(direction=MessageDirection.INBOUND).order_by("-created_at", "-id").first()
        rows.append(
            Row(
                title=chat.display_name or chat.contact_email or "Посетитель сайта",
                subtitle=f"{count} {_plural(count, 'новое сообщение', 'новых сообщения', 'новых сообщений')}",
                text=_clip(last.body, 220) if last else "",
                chips=tuple(chip for chip in (chat.get_channel_display(), chat.contact_email) if chip),
                waiting=human_wait(now - since),
                primary=Action("Ответить", reverse("admin:supportchat_conversation_change", args=[chat.pk])),
                urgent=now - since > timedelta(minutes=15),
            ),
        )
    return Section(
        key="chats",
        layout="cards",
        title="Клиенты пишут в чат",
        hint="Люди в чате и мессенджерах уходят быстро — отвечайте первыми.",
        rows=rows,
        total=total,
        stale=stale,
        stale_url=reverse("admin:supportchat_conversation_changelist"),
        all_url=reverse("admin:supportchat_conversation_changelist"),
    )


def _planned_calls(user: Any) -> Section | None:
    board = build_today_board(user)
    if board is None:
        return None
    rows: list[Row] = []
    total = 0
    can_finish = user.has_perm("crm.change_plannedtouch")
    for group in board["groups"]:
        total += len(group["items"]) + group["more"]
        for card in group["items"]:
            overdue = group["key"] == "overdue"
            call = Action("Позвонить", f"tel:{card['tel']}", external=True) if card["tel"] else None
            open_card = Action("Записать итог", f"{card['url']}#hoocon-card-top")
            rows.append(
                Row(
                    title=card["name"],
                    subtitle="Просрочен перезвон" if overdue else f"Звонок в {card['when']}",
                    waiting=card["when"],
                    primary=call or open_card,
                    secondary=open_card if call else None,
                    finish=_finish(
                        "Завершить",
                        "crm-workspace-finish-call",
                        card["id"],
                        "Завершить звонок? Он будет отмечен закрытым и пропадёт из очереди.",
                    )
                    if can_finish
                    else None,
                    urgent=overdue,
                ),
            )
    return Section(
        key="calls",
        title="Звонки на сегодня",
        hint="Вы обещали перезвонить — клиент ждёт.",
        rows=rows[:SECTION_LIMIT],
        total=total,
        all_url=board["all_url"],
        all_label="Календарь звонков",
    )


def _silent_quotes(user: Any, now: datetime) -> Section | None:
    if not user.has_perm("crm.view_quote"):
        return None
    from crm.models import Quote, QuoteStatus
    from crm.services import scope_quotes_for_manager

    border = now - timedelta(days=QUOTE_SILENCE_DAYS)
    queryset = scope_quotes_for_manager(
        Quote.objects.filter(status=QuoteStatus.SENT, sent_at__lt=border),
        user,
    ).order_by("sent_at")
    total = queryset.count()
    rows = []
    for quote in queryset.select_related("client")[:SECTION_LIMIT]:
        sent = quote.sent_at or quote.created_at
        quote_url = reverse("admin:crm_quote_change", args=[quote.pk])
        client_url = reverse("admin:crm_client_change", args=[quote.client_id])
        rows.append(
            Row(
                title=cast(Any, quote.client).name or cast(Any, quote.client).email,
                subtitle=f"{quote.number or f'КП-{quote.pk}'} отправлено, ответа нет",
                waiting=human_wait(now - sent),
                primary=Action("Написать клиенту", client_url),
                secondary=Action("Открыть КП", quote_url),
                urgent=now - sent > timedelta(days=QUOTE_SILENCE_DAYS * 2),
            ),
        )
    return Section(
        key="quotes",
        title="КП без ответа",
        hint=f"Предложение ушло больше {QUOTE_SILENCE_DAYS} дней назад, клиент молчит. Напомните о себе.",
        rows=rows,
        total=total,
        all_url=reverse("admin:crm_quote_changelist") + "?status__exact=sent",
    )


def _company_follow_ups(user: Any, now: datetime) -> Section | None:
    if not user.has_perm("crm.view_company"):
        return None
    from crm.models import Company

    queryset = Company.objects.filter(
        assignee=user,
        next_contact_at__lte=now,
        next_contact_at__gte=now - timedelta(days=COMPANY_OVERDUE_DAYS),
    ).order_by("next_contact_at")
    total = queryset.count()
    rows = []
    for company in queryset[:SECTION_LIMIT]:
        due = company.next_contact_at or now
        rows.append(
            Row(
                title=company.name,
                subtitle="Пора вернуться к клиенту",
                waiting=human_wait(now - due),
                primary=Action("Открыть карточку", reverse("admin:crm_company_change", args=[company.pk])),
                finish=_finish(
                    "Завершить",
                    "crm-workspace-finish-follow-up",
                    company.pk,
                    "Убрать клиента из очереди? Дата «Вернуться к клиенту» будет снята.",
                )
                if user.has_perm("crm.change_company")
                else None,
                urgent=now - due > timedelta(days=3),
            ),
        )
    return Section(
        key="follow-ups",
        title="Пора вернуться к клиентам",
        hint="Дата «следующего контакта» наступила.",
        rows=rows,
        total=total,
        all_url=reverse("admin:crm_company_changelist"),
        all_label="Все клиенты",
    )


def _leads_in_work(user: Any, now: datetime) -> Section | None:
    if not user.has_perm("leads.view_lead"):
        return None
    from leads.models import Lead

    queryset = Lead.objects.filter(status=Lead.LeadStatus.IN_PROGRESS, assignee=user).order_by("updated_at")
    total = queryset.count()
    rows = []
    for lead in queryset[:SECTION_LIMIT]:
        rows.append(
            Row(
                title=f"{lead.name}, {lead.company}" if lead.company else lead.name,
                subtitle=f"{lead.get_lead_type_display()} · взято в работу, КП не выдано",
                waiting=human_wait(now - lead.updated_at),
                primary=Action("Продолжить", reverse("admin:leads_lead_change", args=[lead.pk])),
                finish=_finish("Завершить", "crm-workspace-finish-lead", lead.pk, _FINISH_LEAD_CONFIRM)
                if user.has_perm("leads.change_lead")
                else None,
            ),
        )
    return Section(
        key="in-work",
        title="Мои заявки в работе",
        hint="Вы их взяли — доведите до КП или закройте.",
        rows=rows,
        total=total,
        all_url=reverse("admin:leads_lead_changelist") + "?status__exact=in_progress",
    )


def _funnel(user: Any, now: datetime) -> list[dict[str, Any]]:
    """The client path as four labelled steps with a counter each."""
    steps: list[dict[str, Any]] = []
    if user.has_perm("leads.view_lead"):
        from leads.models import Lead
        from leads.services import scope_leads_for_manager

        scoped = scope_leads_for_manager(Lead.objects.all(), user)
        steps.append(
            {
                "title": "Заявка",
                "text": "Клиент оставил запрос",
                "count": scoped.filter(status=Lead.LeadStatus.NEW).count(),
                "url": reverse("admin:leads_lead_changelist") + "?status__exact=new",
            },
        )
        steps.append(
            {
                "title": "Связались",
                "text": "Позвонили или написали",
                "count": scoped.filter(status=Lead.LeadStatus.IN_PROGRESS, assignee=user).count(),
                "url": reverse("admin:leads_lead_changelist") + "?status__exact=in_progress",
            },
        )
    if user.has_perm("crm.view_quote"):
        from crm.models import Quote, QuoteStatus
        from crm.services import scope_quotes_for_manager

        scoped_quotes = scope_quotes_for_manager(Quote.objects.all(), user)
        steps.append(
            {
                "title": "КП",
                "text": "Предложение ушло клиенту",
                "count": scoped_quotes.filter(status=QuoteStatus.SENT).count(),
                "url": reverse("admin:crm_quote_changelist") + "?status__exact=sent",
            },
        )
        steps.append(
            {
                "title": "Согласовано",
                "text": "Клиент сказал «да»",
                "count": scoped_quotes.filter(status=QuoteStatus.ACCEPTED).count(),
                "url": reverse("admin:crm_quote_changelist") + "?status__exact=accepted",
            },
        )
    return steps


def _clip(text: str, limit: int = 70) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _plural(number: int, one: str, few: str, many: str) -> str:
    """Russian plural form: 1 сообщение, 2 сообщения, 5 сообщений."""
    tail = number % 100
    if 11 <= tail <= 14:
        return many
    last = number % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many
