"""Bot takeover when a manager stays silent after a client message."""

from __future__ import annotations

from django.conf import settings as dj_settings

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
