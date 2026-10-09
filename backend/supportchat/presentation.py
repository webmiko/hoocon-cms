"""Display labels for chat parties, senders and attachments."""

from __future__ import annotations

from django.contrib.auth.base_user import AbstractBaseUser

from supportchat.models import Conversation, Message, MessageDirection


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


def message_attachment_is_image(message: Message) -> bool:
    """True when the stored attachment should render as an image preview."""
    from supportchat.attachments import is_inline_image

    mime = (message.attachment_mime or "").strip().lower()
    if mime:
        return is_inline_image(mime)
    name = (message.attachment_name or message.attachment.name or "").lower()
    return name.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))


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
        from supportchat.gigachat.disclosure import BOT_SENDER_NAME

        payload = message.raw_payload if isinstance(message.raw_payload, dict) else {}
        if payload.get("ai"):
            return BOT_SENDER_NAME
        if payload.get("ai_handoff"):
            return "Поддержка Hoocon"
        return "Hoocon"
    author_name = staff_public_name(message.author)
    if author_name != "Поддержка":
        return author_name
    return staff_public_name(message.conversation.assignee)
