"""Generate AI replies and detect escalation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from supportchat.gigachat.chat_actions import (
    inbound_continue_with_bot,
    inbound_requests_manager_handoff,
)
from supportchat.gigachat.client import GigachatError, chat_completion
from supportchat.gigachat.policy import resolve_gigachat_model
from supportchat.gigachat.prompts import build_system_prompt
from supportchat.gigachat.triage import (
    is_product_intent,
    is_triage_mode,
    parse_triage_escalation_note,
    triage_handoff_reply,
    triage_site_nav_reply,
)
from supportchat.gigachat.triage_docs import is_document_intent, triage_docs_reply
from supportchat.gigachat.triage_guard import (
    triage_greeting_reply,
    triage_output_blocked,
    uncertain_branch_reply,
)
from supportchat.gigachat.triage_product import (
    build_product_handoff_note,
    product_clarification_already_sent,
    thread_has_product_topic,
    triage_product_clarification_reply,
    triage_product_followup_reply,
)
from supportchat.gigachat.triage_scope import triage_out_of_scope_reply
from supportchat.models import Conversation, Message, MessageDirection

ESCALATE_MARKER = "[ESCALATE]"
_HISTORY_LIMIT = 12
_ESCALATE_PATTERNS = (
    re.compile(r"\[ESCALATE\]", re.IGNORECASE),
    re.compile(r"\b(менеджер|оператор|живой человек)\b", re.IGNORECASE),
    re.compile(r"\b(цена|стоимость|кп|коммерческое предложение)\b", re.IGNORECASE),
)
_CONTINUE_BOT_REPLY = "Хорошо, продолжаем. Задайте вопрос — подскажу раздел сайта, документацию или ссылку на каталог."
_TURN_LIMIT_TEXT = (
    "Могу ещё подсказать раздел сайта или документацию. Для подбора привода "
    "напишите «позовите менеджера», когда будете готовы."
)


@dataclass(frozen=True)
class AiReply:
    """Parsed GigaChat response."""

    text: str
    escalate: bool
    escalation_note: str
    product_clarify: bool = False
    payload_extra: dict[str, object] = field(default_factory=dict)


def turn_limit_reply() -> AiReply:
    """Bot turn cap — suggest typed manager request, no auto handoff."""
    return AiReply(text=_TURN_LIMIT_TEXT, escalate=False, escalation_note="")


def _strip_escalate_marker(text: str) -> str:
    cleaned = re.sub(r"\s*\[ESCALATE\]\s*", "\n", text, flags=re.IGNORECASE).strip()
    return cleaned


def _inbound_payload(inbound_message: Message | None) -> dict[str, object] | None:
    if inbound_message is None:
        return None
    payload = inbound_message.raw_payload
    return payload if isinstance(payload, dict) else None


def _manager_escalation_note(
    user_query: str,
    history: list[dict[str, str]],
    *,
    inbound_payload: dict[str, object] | None,
) -> str:
    if inbound_requests_manager_handoff(user_query, inbound_payload):
        if thread_has_product_topic(history):
            return build_product_handoff_note(history) or "Клиент просит менеджера."
        return "Клиент просит менеджера."
    return build_product_handoff_note(history) or "Клиент запросил менеджера."


def _history_messages(
    conversation: Conversation,
    *,
    up_to_message_id: int | None = None,
) -> list[dict[str, str]]:
    rows = Message.objects.filter(conversation=conversation)
    if up_to_message_id is not None:
        rows = rows.filter(id__lte=up_to_message_id)
    rows = rows.order_by("-created_at", "-id")[:_HISTORY_LIMIT]
    messages: list[dict[str, str]] = []
    for row in reversed(list(rows)):
        if row.direction == MessageDirection.SYSTEM:
            payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
            if payload.get("ai_handoff"):
                continue
        body = (row.body or "").strip()
        if not body:
            continue
        if row.direction == MessageDirection.INBOUND:
            messages.append({"role": "user", "content": body})
        elif row.direction in {MessageDirection.OUTBOUND, MessageDirection.SYSTEM}:
            messages.append({"role": "assistant", "content": body})
    return messages


def generate_ai_reply(
    conversation: Conversation,
    *,
    inbound_message: Message | None = None,
) -> AiReply:
    """Call GigaChat with thread history."""
    if inbound_message is not None:
        if inbound_message.conversation_id != conversation.pk:
            raise GigachatError("Входящее сообщение из другого диалога")
        if inbound_message.direction != MessageDirection.INBOUND:
            raise GigachatError("Ожидалось входящее сообщение клиента")
        user_query = (inbound_message.body or "").strip()
        if not user_query:
            raise GigachatError("Пустое входящее сообщение")
        history = _history_messages(conversation, up_to_message_id=inbound_message.pk)
    else:
        history = _history_messages(conversation)
        if not history or history[-1]["role"] != "user":
            raise GigachatError("Нет входящего сообщения для ответа")
        user_query = history[-1]["content"]
    payload = _inbound_payload(inbound_message)

    if inbound_continue_with_bot(payload):
        return AiReply(text=_CONTINUE_BOT_REPLY, escalate=False, escalation_note="")

    if inbound_requests_manager_handoff(user_query, payload):
        text, _default_note = triage_handoff_reply(user_query)
        note = _manager_escalation_note(user_query, history, inbound_payload=payload)
        return AiReply(text=text, escalate=True, escalation_note=note)

    docs_text = triage_docs_reply(user_query)
    if docs_text:
        return AiReply(text=docs_text, escalate=False, escalation_note="")
    if is_triage_mode():
        scope_text = triage_out_of_scope_reply(user_query)
        if scope_text:
            return AiReply(text=scope_text, escalate=False, escalation_note="")
        nav_text = triage_site_nav_reply(user_query)
        if nav_text:
            return AiReply(text=nav_text, escalate=False, escalation_note="")
        if (
            product_clarification_already_sent(conversation)
            and thread_has_product_topic(history)
            and not is_document_intent(user_query)
        ):
            return AiReply(
                text=triage_product_followup_reply(history),
                escalate=False,
                escalation_note="",
            )
        if is_product_intent(user_query) and not product_clarification_already_sent(conversation):
            return AiReply(
                text=triage_product_clarification_reply(user_query),
                escalate=False,
                escalation_note="",
                product_clarify=True,
            )
        greeting_text = triage_greeting_reply(user_query)
        if greeting_text:
            return AiReply(text=greeting_text, escalate=False, escalation_note="")
        return AiReply(text=uncertain_branch_reply(), escalate=False, escalation_note="")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(user_query=user_query)},
    ]
    messages.extend(history)

    raw = chat_completion(messages, model=resolve_gigachat_model())
    if is_document_intent(user_query):
        docs_fallback = triage_docs_reply(user_query)
        if docs_fallback:
            return AiReply(text=docs_fallback, escalate=False, escalation_note="")
    model_escalate = any(pattern.search(raw) for pattern in _ESCALATE_PATTERNS)
    text = _strip_escalate_marker(raw)
    if is_triage_mode() and triage_output_blocked(text, user_query=user_query):
        if (
            product_clarification_already_sent(conversation)
            and thread_has_product_topic(history)
            and not is_document_intent(user_query)
        ):
            return AiReply(
                text=triage_product_followup_reply(history),
                escalate=False,
                escalation_note="",
            )
        if is_product_intent(user_query):
            return AiReply(
                text=triage_product_clarification_reply(user_query),
                escalate=False,
                escalation_note="",
                product_clarify=True,
            )
        return AiReply(text=uncertain_branch_reply(), escalate=False, escalation_note="")
    if model_escalate and not inbound_requests_manager_handoff(user_query, payload):
        cleaned = text.strip() or "Могу подключить менеджера для точного ответа."
        return AiReply(
            text=f"{cleaned} Напишите «позовите менеджера», когда будете готовы.",
            escalate=False,
            escalation_note="",
        )
    note = ""
    if model_escalate:
        note = parse_triage_escalation_note(text) if is_triage_mode() else ""
        if not note:
            note = "Клиент запросил менеджера или вопрос вне компетенции бота."
    return AiReply(text=text, escalate=model_escalate, escalation_note=note)
