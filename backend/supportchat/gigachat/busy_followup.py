"""Follow-up when managers have not replied to an escalated chat in time."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings as dj_settings
from django.utils import timezone

from supportchat.models import Conversation, ConversationStatus, Message, MessageDirection

_BUSY_FOLLOWUP_TEXT = (
    "Сейчас все менеджеры заняты. Оставьте, пожалуйста, email в этом чате "
    "или в поле «Контакты» вверху — напишем вам, как только освободимся."
)


def escalation_busy_followup_seconds() -> int:
    """Delay after escalation / last client message before the busy follow-up."""
    raw = getattr(dj_settings, "SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS", 300)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 300
    return max(60, seconds)


def build_busy_followup_message(_conversation: Conversation) -> str:
    """Static visitor text when managers are busy."""
    return _BUSY_FOLLOWUP_TEXT


def manager_replied_after_escalation(conversation: Conversation) -> bool:
    """True when staff sent an outbound message after handoff."""
    escalated_at = conversation.ai_escalated_at
    if escalated_at is None:
        return False
    return Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        author__isnull=False,
        created_at__gte=escalated_at,
    ).exists()


def staff_acknowledgement_pending(conversation: Conversation) -> bool:
    """Escalated chat still waiting for the first manager outbound reply."""
    return conversation.ai_escalated_at is not None and not manager_replied_after_escalation(conversation)


def clear_staff_unread_allowed(conversation: Conversation) -> bool:
    """Whether opening the chat or /read/ may clear staff_unread_count."""
    return not staff_acknowledgement_pending(conversation)


def escalation_busy_reference_at(conversation: Conversation) -> datetime | None:
    """When the manager-absence countdown starts or resets."""
    escalated_at = conversation.ai_escalated_at
    if escalated_at is None:
        return None
    last_inbound = (
        Message.objects.filter(
            conversation=conversation,
            direction=MessageDirection.INBOUND,
            created_at__gte=escalated_at,
        )
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return last_inbound or escalated_at


def escalation_busy_deadline_passed(conversation: Conversation) -> bool:
    """True when enough time passed since escalation or the last client message."""
    reference = escalation_busy_reference_at(conversation)
    if reference is None:
        return False
    return timezone.now() >= reference + timedelta(seconds=escalation_busy_followup_seconds())


def escalation_needs_busy_followup(conversation: Conversation) -> bool:
    """True when managers have not replied and the absence delay elapsed."""
    if conversation.ai_escalated_at is None:
        return False
    if conversation.status != ConversationStatus.OPEN:
        return False
    if manager_replied_after_escalation(conversation):
        return False
    if (conversation.contact_email or "").strip():
        return False
    if Message.objects.filter(
        conversation=conversation,
        raw_payload__ai_busy_followup=True,
    ).exists():
        return False
    if not escalation_busy_deadline_passed(conversation):
        return False
    return True
