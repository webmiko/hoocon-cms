"""Follow-up when managers have not opened an escalated chat in time."""

from __future__ import annotations

from django.conf import settings as dj_settings

from supportchat.models import Conversation, ConversationStatus, Message, MessageDirection

_BUSY_FOLLOWUP_TEXT = (
    "Сейчас все менеджеры заняты. Оставьте, пожалуйста, email в этом чате "
    "или в поле «Контакты» вверху — напишем вам, как только освободимся."
)


def escalation_busy_followup_seconds() -> int:
    """Delay after escalation before the busy follow-up message."""
    raw = getattr(dj_settings, "SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS", 300)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 300
    return max(60, seconds)


def build_busy_followup_message(_conversation: Conversation) -> str:
    """Static visitor text when managers are busy."""
    return _BUSY_FOLLOWUP_TEXT


def escalation_needs_busy_followup(conversation: Conversation) -> bool:
    """True when managers have not viewed/replied and we have no email yet."""
    if conversation.ai_escalated_at is None:
        return False
    if conversation.status != ConversationStatus.OPEN:
        return False
    if conversation.staff_unread_count <= 0:
        return False
    if (conversation.contact_email or "").strip():
        return False
    if Message.objects.filter(
        conversation=conversation,
        raw_payload__ai_busy_followup=True,
    ).exists():
        return False
    if Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        created_at__gte=conversation.ai_escalated_at,
    ).exists():
        return False
    return True
