"""Conversation helpers: session web + messenger ingest + staff reply."""

from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from supportchat.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    touch_conversation_message,
)
from supportchat.schedule import ensure_default_schedule, is_open_now

SESSION_KEY = "support_session_id"
_MAX_BODY_LEN = 4000


class SupportChatError(Exception):
    """Domain error for support chat operations."""


def get_or_create_web_session_id(request: HttpRequest) -> str:
    """Stable anonymous session id stored in Django session."""
    existing = request.session.get(SESSION_KEY)
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    new_id = str(uuid.uuid4())
    request.session[SESSION_KEY] = new_id
    request.session.modified = True
    return new_id


def get_web_conversation(request: HttpRequest) -> Conversation | None:
    """Current web conversation for this session, if any."""
    session_id = request.session.get(SESSION_KEY)
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    return Conversation.objects.filter(
        channel=Channel.WEB,
        external_user_id=session_id.strip(),
    ).first()


def start_or_resume_web_conversation(
    request: HttpRequest,
    *,
    display_name: str = "",
    contact_email: str = "",
) -> Conversation:
    """Create or resume the web Conversation for this browser session."""
    session_id = get_or_create_web_session_id(request)
    conv, created = Conversation.objects.get_or_create(
        channel=Channel.WEB,
        external_user_id=session_id,
        defaults={
            "display_name": (display_name or "").strip()[:200],
            "contact_email": (contact_email or "").strip()[:254],
            "status": ConversationStatus.OPEN,
        },
    )
    if not created:
        updates: list[str] = []
        name = (display_name or "").strip()[:200]
        email = (contact_email or "").strip()[:254]
        if name and name != conv.display_name:
            conv.display_name = name
            updates.append("display_name")
        if email and email != conv.contact_email:
            conv.contact_email = email
            updates.append("contact_email")
        if conv.status == ConversationStatus.CLOSED:
            conv.status = ConversationStatus.OPEN
            updates.append("status")
        if updates:
            updates.append("updated_at")
            conv.save(update_fields=updates)
    return conv


def _sanitize_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        raise SupportChatError("Пустое сообщение")
    if len(text) > _MAX_BODY_LEN:
        raise SupportChatError(f"Сообщение длиннее {_MAX_BODY_LEN} символов")
    return text


@transaction.atomic
def add_inbound_message(
    conversation: Conversation,
    body: str,
    *,
    external_message_id: str = "",
    raw_payload: dict[str, Any] | None = None,
    display_name: str = "",
) -> tuple[Message, Message | None]:
    """Append client message; optionally system auto-reply outside hours.

    Returns:
        (inbound_message, auto_reply_or_None). Duplicate external id →
        existing inbound, no auto-reply.
    """
    ext = (external_message_id or "").strip()
    if ext:
        existing = Message.objects.filter(
            conversation=conversation,
            external_message_id=ext,
        ).first()
        if existing is not None:
            return existing, None

    text = _sanitize_body(body)
    open_now = is_open_now()
    inbound = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        body=text,
        external_message_id=ext,
        outside_hours=not open_now,
        raw_payload=raw_payload,
    )
    if display_name.strip() and not conversation.display_name:
        conversation.display_name = display_name.strip()[:200]
        conversation.save(update_fields=["display_name", "updated_at"])
    touch_conversation_message(conversation, inbound=True)

    auto: Message | None = None
    if not open_now:
        schedule = ensure_default_schedule()
        reply_text = (schedule.auto_reply_outside_hours or "").strip()
        if reply_text:
            auto = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.SYSTEM,
                body=reply_text,
                outside_hours=True,
            )
            touch_conversation_message(conversation, inbound=False)
    _schedule_staff_support_push(conversation.pk)
    return inbound, auto


def _schedule_staff_support_push(conversation_id: int) -> None:
    """Enqueue staff Web Push after commit."""
    from django.db import transaction

    def _enqueue() -> None:
        from webpush.tasks import notify_staff_support_inbound

        notify_staff_support_inbound.delay(conversation_id)

    transaction.on_commit(_enqueue)


@transaction.atomic
def add_staff_reply(
    conversation: Conversation,
    body: str,
    *,
    author: AbstractBaseUser | None,
) -> Message:
    """Staff outbound message; clears staff unread."""
    text = _sanitize_body(body)
    author_user = author if author is not None and getattr(author, "pk", None) else None
    msg = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.OUTBOUND,
        body=text,
        author=author_user,  # type: ignore[misc]
        outside_hours=False,
    )
    conversation.staff_unread_count = 0
    conversation.last_message_at = timezone.now()
    conversation.status = ConversationStatus.OPEN
    conversation.save(
        update_fields=["staff_unread_count", "last_message_at", "status", "updated_at"],
    )
    _schedule_visitor_support_push(conversation.pk)
    return msg


def _schedule_visitor_support_push(conversation_id: int) -> None:
    """Enqueue visitor Web Push after commit (web channel only)."""
    from django.db import transaction

    def _enqueue() -> None:
        from webpush.tasks import notify_visitor_support_reply

        notify_visitor_support_reply.delay(conversation_id)

    transaction.on_commit(_enqueue)


def count_staff_unread() -> int:
    """Total unread inbound messages across open conversations."""
    from django.db.models import Sum

    total = Conversation.objects.filter(status=ConversationStatus.OPEN).aggregate(s=Sum("staff_unread_count")).get("s")
    return int(total or 0)


def get_or_create_messenger_conversation(
    channel: str,
    external_user_id: str,
    *,
    display_name: str = "",
) -> Conversation:
    """Messenger thread keyed by channel + external user id."""
    ext = (external_user_id or "").strip()
    if not ext:
        raise SupportChatError("Пустой external_user_id")
    conv, created = Conversation.objects.get_or_create(
        channel=channel,
        external_user_id=ext,
        defaults={
            "display_name": (display_name or "").strip()[:200],
            "status": ConversationStatus.OPEN,
        },
    )
    if not created and display_name.strip() and not conv.display_name:
        conv.display_name = display_name.strip()[:200]
        conv.save(update_fields=["display_name", "updated_at"])
    if conv.status == ConversationStatus.CLOSED:
        conv.status = ConversationStatus.OPEN
        conv.save(update_fields=["status", "updated_at"])
    return conv
