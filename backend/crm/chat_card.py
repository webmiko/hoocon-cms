"""Top strip of a chat page: what to do with this dialog right now.

The messenger itself is fine. What was missing is the step around it: who
owns the dialog, is there a client card, when to close it, and how to turn
a question about a price into an offer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.urls import reverse

from crm.lead_card import Button


@dataclass
class ChatCard:
    """Everything the strip template needs."""

    state: str
    headline: str
    hint: str = ""
    buttons: list[Button] = field(default_factory=list)


def _name(user: Any) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.get_username()


def build_chat_card(conversation: Any, user: Any) -> ChatCard:
    """Strip for one dialog as seen by ``user``."""
    from supportchat.models import ConversationStatus

    can_change = user.has_perm("supportchat.change_conversation")
    client = conversation.client if conversation.client_id else None
    lead = conversation.lead if conversation.lead_id else None

    links: list[Button] = []
    if client is not None and user.has_perm("crm.view_client"):
        links.append(Button("Карточка клиента", reverse("admin:crm_client_change", args=[client.pk])))
    if lead is not None and user.has_perm("leads.view_lead"):
        links.append(Button(f"Заявка №{lead.pk}", reverse("admin:leads_lead_change", args=[lead.pk])))
    quote = (
        [Button("Создать КП", reverse("admin:crm_quote_add") + f"?client={client.pk}")]
        if client is not None and user.has_perm("crm.add_quote")
        else []
    )

    if conversation.status == ConversationStatus.CLOSED:
        return ChatCard(
            "closed", "Диалог закрыт", "Переписка сохранена. Если клиент написал снова, диалог откроется сам.", links
        )
    if conversation.assignee_id is None:
        buttons = (
            [
                Button(
                    "Взять диалог", reverse("crm-workspace-take-chat", args=[conversation.pk]), post=True, primary=True
                )
            ]
            if can_change
            else []
        )
        return ChatCard(
            "free",
            "Диалог свободен: возьмите его",
            "После этого он закрепится за вами, и коллеги увидят, что им занимаются.",
            [*buttons, *links],
        )
    if conversation.assignee_id != user.pk:
        return ChatCard(
            "other",
            f"Диалог ведёт {_name(conversation.assignee)}",
            "Вы видите переписку, но отвечать лучше тому, кто его взял.",
            links,
        )

    if client is None:
        hint = (
            "Клиента в CRM пока нет. Попросите почту или телефон: с ними появится карточка и можно будет создать КП."
        )
    else:
        hint = "Ответьте в чате ниже. Если клиент спрашивает цену, создайте КП. Когда вопрос решён, закройте диалог."
    buttons = [*quote, *links]
    if can_change:
        buttons.append(
            Button("Закрыть диалог", reverse("crm-workspace-close-chat", args=[conversation.pk]), post=True)
        )
    return ChatCard("mine", "Ответьте клиенту в чате", hint, buttons)
