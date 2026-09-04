"""Conversation helpers: session web + messenger ingest + staff reply."""

from __future__ import annotations

import uuid
from datetime import timedelta
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
    # Web inbound on a closed thread must reopen (same as messenger).
    if conversation.status == ConversationStatus.CLOSED:
        conversation.status = ConversationStatus.OPEN
        conversation.save(update_fields=["status", "updated_at"])
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
        # At most one outside-hours auto-reply per conversation per 24h.
        already = Message.objects.filter(
            conversation=conversation,
            direction=MessageDirection.SYSTEM,
            outside_hours=True,
            created_at__gte=timezone.now() - timedelta(hours=24),
        ).exists()
        if reply_text and not already:
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
    """Enqueue staff Web Push + FCM after commit."""
    from django.db import transaction

    def _enqueue() -> None:
        from webpush.tasks import notify_staff_support_inbound

        notify_staff_support_inbound.delay(conversation_id)
        try:
            from staff_api.tasks import notify_staff_fcm_support

            notify_staff_fcm_support.delay(conversation_id)
        except Exception:  # noqa: BLE001 — FCM optional / app may be absent
            pass

    transaction.on_commit(_enqueue)


@transaction.atomic
def add_staff_reply(
    conversation: Conversation,
    body: str,
    *,
    author: AbstractBaseUser | None,
) -> Message:
    """Staff outbound message; clears staff unread; claims assignee if empty."""
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
    update_fields = ["staff_unread_count", "last_message_at", "status", "updated_at"]
    if author_user is not None and conversation.assignee_id is None:
        conversation.assignee = author_user  # type: ignore[assignment]
        update_fields.append("assignee")
    conversation.save(update_fields=update_fields)
    _schedule_visitor_support_push(conversation.pk)
    return msg


def staff_public_name(user: AbstractBaseUser | None) -> str:
    """Public label for a staff user (first_name; never email/username)."""
    if user is None:
        return "Поддержка"
    first = (getattr(user, "first_name", "") or "").strip()
    if first:
        return first[:80]
    full = ""
    getter = getattr(user, "get_full_name", None)
    if callable(getter):
        full = (getter() or "").strip()
    if full:
        return full[:80]
    return "Поддержка"


def conversation_party_label(conversation: Conversation) -> str:
    """Staff hub title: «Имя · Компания» or «Пользователь · телефон/email».

    Prefer CRM client, then linked lead, then widget display_name. Anonymous
    visitors without a name get «Пользователь» plus phone or email. Channel
    name is never part of the title (shown separately in UI meta).
    """
    name = ""
    company = ""
    phone = ""
    client = getattr(conversation, "client", None)
    lead = getattr(conversation, "lead", None)
    if client is not None:
        name = (getattr(client, "name", None) or "").strip()
        company = (getattr(client, "company", None) or "").strip()
        phone = (getattr(client, "phone", None) or "").strip()
    if lead is not None:
        if not name:
            name = (getattr(lead, "name", None) or "").strip()
        if not company:
            company = (getattr(lead, "company", None) or "").strip()
        if not phone:
            phone = (getattr(lead, "phone", None) or "").strip()
    display = (conversation.display_name or "").strip()
    if not name and display:
        name = display

    if name or company:
        if name and company and name.casefold() != company.casefold():
            return f"{name} · {company}"[:200]
        return (name or company)[:200]

    email = (conversation.contact_email or "").strip()
    if phone:
        return f"Пользователь · {phone}"[:200]
    if email:
        return f"Пользователь · {email}"[:200]
    # Channel belongs in subtitle/meta — never as the hub title.
    return "Пользователь"


def conversation_party_phone(conversation: Conversation) -> str:
    """Best-effort phone for staff UI (client → lead)."""
    client = getattr(conversation, "client", None)
    if client is not None:
        phone = (getattr(client, "phone", None) or "").strip()
        if phone:
            return phone[:64]
    lead = getattr(conversation, "lead", None)
    if lead is not None:
        phone = (getattr(lead, "phone", None) or "").strip()
        if phone:
            return phone[:64]
    return ""


def conversation_party_company(conversation: Conversation) -> str:
    """Best-effort company for staff UI (client → lead)."""
    client = getattr(conversation, "client", None)
    if client is not None:
        company = (getattr(client, "company", None) or "").strip()
        if company:
            return company[:200]
    lead = getattr(conversation, "lead", None)
    if lead is not None:
        company = (getattr(lead, "company", None) or "").strip()
        if company:
            return company[:200]
    return ""


def message_sender_name(message: Message, *, staff_view: bool = False) -> str:
    """Name next to a chat bubble (visitor UI or Admin messenger)."""
    if message.direction == MessageDirection.INBOUND:
        if staff_view:
            label = conversation_party_label(message.conversation)
            return label.split(" · ", 1)[0][:80]
        label = (message.conversation.display_name or "").strip()
        if label:
            return label[:80]
        return "Вы"
    if message.direction == MessageDirection.SYSTEM:
        return "Hoocon"
    author_name = staff_public_name(message.author)
    if author_name != "Поддержка":
        return author_name
    return staff_public_name(message.conversation.assignee)


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


def delete_unlinked_conversation(conversation: Conversation) -> None:
    """Hard-delete a support thread that is not linked to a CRM client.

    Linked CRM chats must stay for history; managers clear anonymous / spam
    web sessions from the mobile app instead.
    """
    if conversation.client_id is not None:
        raise SupportChatError("Нельзя удалить диалог, привязанный к клиенту CRM.")
    conversation.delete()


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
