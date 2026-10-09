"""Bot takeover when a manager stays silent after a client message.

Two stages, one policy:

- the bot handed the chat off and no manager has picked it up yet →
  wait for a human (``escalation_takeover_seconds``); the busy follow-up
  «менеджеры заняты» always fires first;
- a manager already led the chat and went quiet → the bot answers after
  ``manager_reply_timeout_seconds`` of silence.
"""

from __future__ import annotations

import math
from datetime import timedelta

from django.conf import settings as dj_settings
from django.utils import timezone

from supportchat.gigachat.busy_followup import (
    escalation_busy_followup_seconds,
    manager_replied_after_escalation,
)
from supportchat.models import Conversation, Message, MessageDirection


def manager_reply_timeout_seconds() -> int:
    """Silence window before the bot takes the dialog back.

    Kept under one minute so visitors never wait longer than that for
    a response (SUPPORT_MANAGER_REPLY_TIMEOUT_SECONDS).
    """
    raw = getattr(dj_settings, "SUPPORT_MANAGER_REPLY_TIMEOUT_SECONDS", 45)
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 45
    return max(10, seconds)


def manager_engaged_since(conversation: Conversation, *, message_id: int) -> bool:
    """Staff outbound reply exists after the given inbound message."""
    return Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        author__isnull=False,
        id__gt=message_id,
    ).exists()


def ai_resume_stale_escalation_minutes() -> int:
    """Manager silence on an escalated chat before the bot takes it back."""
    raw = getattr(dj_settings, "SUPPORT_AI_RESUME_STALE_MINUTES", 30)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def escalation_takeover_seconds() -> int:
    """How long a fresh handoff stays with humans before the bot resumes.

    Never shorter than the busy follow-up plus one reply window, so the
    visitor is offered «оставьте email» before the bot comes back.
    """
    return max(
        ai_resume_stale_escalation_minutes() * 60,
        escalation_busy_followup_seconds() + manager_reply_timeout_seconds(),
    )


def escalation_awaiting_manager(conversation: Conversation) -> bool:
    """Bot handed off and no manager picked the chat up (assignee / reply)."""
    return (
        conversation.ai_escalated_at is not None
        and conversation.assignee_id is None
        and not manager_replied_after_escalation(conversation)
    )


def takeover_delay_seconds(conversation: Conversation) -> int:
    """Countdown for the silence watchdog of this conversation."""
    reply_window = manager_reply_timeout_seconds()
    if not escalation_awaiting_manager(conversation):
        return reply_window
    escalated_at = conversation.ai_escalated_at
    assert escalated_at is not None
    due = escalated_at + timedelta(seconds=escalation_takeover_seconds())
    return max(reply_window, math.ceil((due - timezone.now()).total_seconds()))


def escalation_takeover_due(conversation: Conversation) -> bool:
    """False while a fresh handoff is still waiting for a human."""
    if not escalation_awaiting_manager(conversation):
        return True
    escalated_at = conversation.ai_escalated_at
    assert escalated_at is not None
    return timezone.now() >= escalated_at + timedelta(seconds=escalation_takeover_seconds())
