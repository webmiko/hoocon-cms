"""Conversation helpers: session web + messenger ingest + staff reply."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from cabinet.auth import session_owns_email
from config.pdn import PDN_CONSENT_REQUIRED, stamp_pdn_consent
from supportchat.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    touch_conversation_message,
)
from supportchat.presentation import (
    conversation_party_company,
    conversation_party_label,
    conversation_party_phone,
    staff_public_name,
)
from supportchat.schedule import ensure_default_schedule, is_open_now

SESSION_KEY = "support_session_id"
_MAX_BODY_LEN = 4000


class SupportChatError(Exception):
    """Domain error for support chat operations."""


def _reopen_conversation(conversation: Conversation) -> None:
    """CLOSED → OPEN + fresh bot session (AI state and assignee reset)."""
    conversation.status = ConversationStatus.OPEN
    conversation.ai_active = True
    conversation.ai_escalated_at = None
    conversation.ai_turn_count = 0
    conversation.assignee = None
    conversation.save(
        update_fields=[
            "status",
            "ai_active",
            "ai_escalated_at",
            "ai_turn_count",
            "assignee",
            "updated_at",
        ],
    )


logger = logging.getLogger("hoocon.supportchat")


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


def _auto_link_client(conversation: Conversation) -> None:
    """Attach the CRM client card by ``contact_email`` (create it if absent).

    Same dossier rule as leads: every contact channel lands on the client
    card. Runs only while ``conversation.client`` is unset — a manual staff
    link always wins. Updates the row in place and the instance's
    ``client_id`` for callers that keep it.
    """
    email = (conversation.contact_email or "").strip()
    if conversation.client_id is not None or not email:
        return
    from crm.services import get_or_create_client_by_email

    client = get_or_create_client_by_email(
        email=email,
        name=conversation.display_name,
    )
    Conversation.objects.filter(pk=conversation.pk, client__isnull=True).update(
        client_id=client.pk,
    )
    conversation.client_id = client.pk


def start_or_resume_web_conversation(
    request: HttpRequest,
    *,
    display_name: str = "",
    contact_email: str = "",
    page_url: str = "",
    pdn_consent: bool = False,
) -> Conversation:
    """Create or resume the web Conversation for this browser session.

    Name/email are stored only with PDN consent — given now or earlier in
    this thread; otherwise :class:`SupportChatError` and nothing is saved.
    """
    session_id = get_or_create_web_session_id(request)
    page = (page_url or "").strip()[:500]
    name = (display_name or "").strip()[:200]
    email = (contact_email or "").strip()[:254]
    with transaction.atomic():
        conv, created = Conversation.objects.get_or_create(
            channel=Channel.WEB,
            external_user_id=session_id,
            defaults={"page_url": page, "status": ConversationStatus.OPEN},
        )
        # Re-lock so concurrent resume/update for the same session does not
        # overwrite display_name/contact_email/status.
        conv = Conversation.objects.select_for_update().get(pk=conv.pk)
        if (name or email) and not pdn_consent and conv.pdn_consent_at is None:
            raise SupportChatError(PDN_CONSENT_REQUIRED)
        updates: list[str] = []
        if name and name != conv.display_name:
            conv.display_name = name
            updates.append("display_name")
        if email and email != conv.contact_email:
            conv.contact_email = email
            updates.append("contact_email")
        if pdn_consent and (name or email):
            stamp_pdn_consent(conv)
            updates += ["pdn_consent_at", "pdn_policy_version"]
        if not created:
            if page and page != conv.page_url:
                conv.page_url = page
                updates.append("page_url")
            if conv.status == ConversationStatus.CLOSED:
                _reopen_conversation(conv)
        if updates:
            updates.append("updated_at")
            conv.save(update_fields=updates)
        if not conv.contact_verified and session_owns_email(request, conv.contact_email):
            conv.contact_verified = True
            conv.save(update_fields=["contact_verified"])
    _auto_link_client(conv)
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
    page_url: str = "",
    attachment: Any | None = None,
    attachment_name: str = "",
    attachment_mime: str = "",
) -> tuple[Message, Message | None]:
    """Append client message; optionally system auto-reply outside hours.

    Returns:
        (inbound_message, auto_reply_or_None). Duplicate external id →
        existing inbound, no auto-reply.
    """
    ext = (external_message_id or "").strip()
    # Lock the conversation so concurrent inbound messages are serialized;
    # this also makes the "first inbound" check reliable.
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    if ext:
        existing = Message.objects.filter(
            conversation=conversation,
            external_message_id=ext,
        ).first()
        if existing is not None:
            return existing, None

    if attachment is not None:
        from supportchat.attachments import safe_attachment_mime

        attachment_mime = safe_attachment_mime(attachment, attachment_mime)
    if (body or "").strip():
        text = _sanitize_body(body)
    elif attachment is not None:
        text = f"📎 {attachment_name or 'файл'}"
    else:
        text = _sanitize_body(body)  # raises «Пустое сообщение»
    open_now = is_open_now()
    # First client message in the thread → email managers (attention ping).
    is_first_inbound = not Message.objects.filter(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
    ).exists()
    # Web inbound on a closed thread must reopen (same as messenger);
    # reopened thread = fresh session for the bot.
    if conversation.status == ConversationStatus.CLOSED:
        _reopen_conversation(conversation)
    inbound = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.INBOUND,
        body=text,
        external_message_id=ext,
        outside_hours=not open_now,
        raw_payload=raw_payload,
        attachment_name=(attachment_name or "")[:255] if attachment is not None else "",
        attachment_mime=(attachment_mime or "")[:100] if attachment is not None else "",
    )
    if attachment is not None:
        inbound.attachment.save(attachment_name or "file", attachment)
    conv_updates: list[str] = []
    if display_name.strip() and not conversation.display_name:
        conversation.display_name = display_name.strip()[:200]
        conv_updates.append("display_name")
    page = (page_url or "").strip()[:500]
    if page and page != conversation.page_url:
        conversation.page_url = page
        conv_updates.append("page_url")
    if conv_updates:
        conv_updates.append("updated_at")
        conversation.save(update_fields=conv_updates)
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
    _schedule_staff_support_push(
        conversation.pk,
        message_id=inbound.pk,
        first_inbound=is_first_inbound,
    )
    _schedule_ai_reply(conversation.pk, inbound.pk)
    from supportchat.gigachat.busy_followup import staff_acknowledgement_pending
    from supportchat.gigachat.policy import conversation_ai_eligible

    if staff_acknowledgement_pending(conversation):
        from supportchat.tasks import _schedule_escalation_busy_followup

        _schedule_escalation_busy_followup(conversation.pk)
    if not conversation_ai_eligible(conversation):
        # Диалог у человека — бот подхватит его, если менеджер не ответит вовремя.
        from supportchat.tasks import _schedule_manager_silence_watchdog

        _schedule_manager_silence_watchdog(conversation.pk, inbound.pk)
    return inbound, auto


def staff_push_debounce_seconds() -> int:
    """Delay before staff push so a burst of client messages = one alert."""
    from django.conf import settings as dj_settings

    raw = getattr(dj_settings, "SUPPORT_STAFF_PUSH_DEBOUNCE_SECONDS", 20)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 20


def inbound_superseded(conversation_id: int, inbound_message_id: int) -> bool:
    """Newer inbound exists → a later debounced push task will fire instead."""
    return Message.objects.filter(
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        id__gt=inbound_message_id,
    ).exists()


_STAFF_PUSH_DEDUP_TTL = 6 * 3600


def claim_staff_support_push(
    channel: str,
    conversation_id: int,
    inbound_message_id: int | None = None,
) -> bool:
    """Claim the staff alert for an inbound on this channel (atomic).

    One inbound message must produce at most one staff push per channel.
    Without it the debounced inbound task and the immediate escalation
    task (``message_id=None``) both deliver the same alert.
    """
    from django.core.cache import cache

    if inbound_message_id is None:
        inbound_message_id = (
            Message.objects.filter(
                conversation_id=conversation_id,
                direction=MessageDirection.INBOUND,
            )
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
        )
    if inbound_message_id is None:
        return True
    key = f"support-staff-push:{channel}:{conversation_id}:{inbound_message_id}"
    return bool(cache.add(key, 1, timeout=_STAFF_PUSH_DEDUP_TTL))


def _schedule_ai_reply(conversation_id: int, inbound_message_id: int) -> None:
    """Enqueue GigaChat assistant reply after commit."""
    from django.db import transaction

    from supportchat.gigachat.policy import ai_assistant_enabled

    if not ai_assistant_enabled():
        return

    def _enqueue() -> None:
        from supportchat.tasks import gigachat_reply

        gigachat_reply.delay(conversation_id, inbound_message_id)

    transaction.on_commit(_enqueue)


def _schedule_staff_support_push(
    conversation_id: int,
    *,
    message_id: int | None = None,
    first_inbound: bool = False,
) -> None:
    """Enqueue staff Web Push + FCM (+ first-inbound email) after commit."""
    from django.db import transaction

    def _enqueue() -> None:
        from accounts.tasks import notify_staff_max_support, notify_staff_telegram_support
        from webpush.tasks import notify_staff_support_inbound

        # Дебаунс: задачи с message_id ждут и пропускают себя, если пришло
        # более новое inbound — бёрст клиента даёт один пуш, а не серию.
        countdown = staff_push_debounce_seconds() if message_id else 0
        notify_staff_support_inbound.apply_async(
            args=[conversation_id, message_id],
            countdown=countdown,
        )
        notify_staff_telegram_support.apply_async(
            args=[conversation_id, message_id],
            countdown=countdown,
        )
        notify_staff_max_support.apply_async(
            args=[conversation_id, message_id],
            countdown=countdown,
        )
        try:
            from staff_api.tasks import notify_staff_fcm_support

            notify_staff_fcm_support.apply_async(
                args=[conversation_id, message_id],
                countdown=countdown,
            )
        except Exception:  # noqa: BLE001 — FCM optional / app may be absent
            logger.exception("fcm_support_enqueue_failed conversation_id=%s", conversation_id)
        if first_inbound and message_id is not None:
            from supportchat.tasks import send_support_first_inbound_notification

            send_support_first_inbound_notification.delay(conversation_id, message_id)

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
    # Lock before read-modify-write so two staff replies cannot race on
    # assignee and unread counter.
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
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
    if conversation.ai_active:
        conversation.ai_active = False
        update_fields.append("ai_active")
    conversation.save(update_fields=update_fields)
    _schedule_visitor_support_push(conversation.pk)
    _schedule_superuser_staff_reply_telegram(conversation.pk, author_user)
    _schedule_retire_max_support_alert(conversation.pk, author_user)
    _schedule_retire_telegram_support_alert(conversation.pk, author_user)
    return msg


def _schedule_retire_telegram_support_alert(
    conversation_id: int,
    author: AbstractBaseUser | None,
) -> None:
    """After a staff reply, retire «Ответить» buttons on Telegram alerts."""

    author_id = getattr(author, "pk", None)

    def _enqueue() -> None:
        from accounts.telegram_tasks import retire_telegram_support_alert

        retire_telegram_support_alert.delay(conversation_id, author_id)

    transaction.on_commit(_enqueue)


@transaction.atomic
def add_staff_note(
    conversation: Conversation,
    body: str,
    *,
    author: AbstractBaseUser | None,
) -> Message:
    """Internal staff-only note: never delivered to the client channel."""
    text = _sanitize_body(body)
    if not text:
        raise SupportChatError("Пустая заметка.")
    author_user = author if author is not None and getattr(author, "pk", None) else None
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    msg = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.NOTE,
        body=text,
        author=author_user,  # type: ignore[misc]
        outside_hours=False,
    )
    conversation.staff_unread_count = 0
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["staff_unread_count", "last_message_at", "updated_at"])
    return msg


def _schedule_retire_max_support_alert(
    conversation_id: int,
    author: AbstractBaseUser | None,
) -> None:
    """After a staff reply, retire «Ответить» buttons on other staff alerts."""
    from django.db import transaction

    author_id = getattr(author, "pk", None)

    def _enqueue() -> None:
        from accounts.max_tasks import retire_max_support_alert

        retire_max_support_alert.delay(conversation_id, author_id)

    transaction.on_commit(_enqueue)


def _schedule_superuser_staff_reply_telegram(
    conversation_id: int,
    author: AbstractBaseUser | None,
) -> None:
    """Notify superusers that staff replied in support chat."""
    from django.db import transaction

    author_label = staff_public_name(author)

    def _enqueue() -> None:
        from accounts.tasks import notify_superuser_telegram_crm

        notify_superuser_telegram_crm.delay(
            "Ответ в поддержке",
            f"{author_label}: ответ клиенту",
            f"/admin/supportchat/conversation/{conversation_id}/change/",
        )

    transaction.on_commit(_enqueue)


def compose_staff_support_alert(
    conversation: Conversation,
    *,
    inbound_message_id: int | None = None,
    reply_hint: str = "",
) -> tuple[str, str]:
    """Title/body for a staff alert on inbound support message (TG + MAX).

    Includes the client text itself so the manager sees the question
    without opening Admin.
    """
    from sitesettings.staff_push import staff_support_push_copy

    label = conversation.display_name or conversation.get_channel_display()
    title, fallback_body = staff_support_push_copy(label=label)
    title = f"{title} · #{conversation.pk}"

    inbound: Message | None = None
    if inbound_message_id is not None:
        inbound = Message.objects.filter(
            pk=inbound_message_id,
            conversation_id=conversation.pk,
            direction=MessageDirection.INBOUND,
        ).first()
    if inbound is None:
        inbound = (
            Message.objects.filter(
                conversation_id=conversation.pk,
                direction=MessageDirection.INBOUND,
            )
            .order_by("-id")
            .first()
        )

    parts: list[str] = []
    if inbound is not None and inbound.attachment:
        name = inbound.attachment_name or "файл"
        admin_url = build_conversation_admin_url(conversation.pk)
        parts.append(f"📎 {name}: {admin_url}")
    if inbound is not None:
        snippet = (inbound.body or "").strip().replace("\n", " ")
        if len(snippet) > 400:
            snippet = snippet[:399].rstrip() + "…"
        if snippet:
            channel_label = conversation.get_channel_display()
            parts.append(f"{channel_label} · {label}:\n«{snippet}»")
    if not parts:
        parts.append(fallback_body)
    page = (getattr(conversation, "page_url", "") or "").strip()
    if page:
        parts.append(f"Страница: {page}")
    hint = (reply_hint or "").strip()
    if hint:
        parts.append(hint)
    return title, "\n\n".join(parts)


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


def resolve_support_notify_recipients(conversation: Conversation) -> list[str]:
    """Email recipients for a new support thread (first inbound only).

    Active staff assignee with email → that address. Otherwise the same
    sales list as leads (``LEAD_NOTIFY_EMAIL``).
    """
    from django.conf import settings

    from leads.services import parse_notify_emails

    assignee = getattr(conversation, "assignee", None)
    if assignee is not None and getattr(assignee, "is_active", False) and getattr(assignee, "is_staff", False):
        addr = (getattr(assignee, "email", "") or "").strip()
        if addr:
            return parse_notify_emails(addr)
    return parse_notify_emails(getattr(settings, "LEAD_NOTIFY_EMAIL", "") or "")


def build_conversation_admin_url(conversation_id: int) -> str:
    """Absolute Admin change URL for a support conversation."""
    from django.conf import settings
    from django.urls import reverse

    site = getattr(settings, "SITE_URL", "").rstrip("/") or "https://hoocon.ru"
    path = reverse("admin:supportchat_conversation_change", args=[conversation_id])
    return f"{site}{path}"


def render_support_first_inbound_notification(
    conversation: Conversation,
    message: Message,
) -> tuple[str, str, str]:
    """Build subject + text/HTML for the first-inbound support email."""
    from django.conf import settings
    from django.template.loader import render_to_string

    site_url = getattr(settings, "SITE_URL", "").rstrip("/") or "https://hoocon.ru"
    party = conversation_party_label(conversation)
    preview = (message.body or "").strip()
    if len(preview) > 400:
        preview = preview[:397] + "…"
    phone = conversation_party_phone(conversation)
    company = conversation_party_company(conversation)
    context = {
        "conversation": conversation,
        "message": message,
        "party_label": party,
        "channel_display": conversation.get_channel_display(),
        "preview": preview,
        "phone": phone,
        "company": company,
        "contact_email": (conversation.contact_email or "").strip(),
        "site_url": site_url,
        "admin_url": build_conversation_admin_url(conversation.pk),
    }
    subject = f"Новый чат поддержки #{conversation.pk}: {party}"
    text_body = render_to_string(
        "supportchat/email/first_inbound.txt",
        context,
    ).strip()
    html_body = render_to_string(
        "supportchat/email/first_inbound.html",
        context,
    ).strip()
    return subject, text_body, html_body


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
        raise SupportChatError("Пустой внешний идентификатор")
    with transaction.atomic():
        conv, created = Conversation.objects.get_or_create(
            channel=channel,
            external_user_id=ext,
            defaults={
                "display_name": (display_name or "").strip()[:200],
                "status": ConversationStatus.OPEN,
            },
        )
        # Lock the row before any status/display_name update so concurrent
        # messenger updates for the same external id are serialized.
        conv = Conversation.objects.select_for_update().get(pk=conv.pk)
        if not created and display_name.strip() and not conv.display_name:
            conv.display_name = display_name.strip()[:200]
            conv.save(update_fields=["display_name", "updated_at"])
        if conv.status == ConversationStatus.CLOSED:
            _reopen_conversation(conv)
    return conv


def chat_faq_items(*, limit: int | None = None) -> list[dict[str, str | int]]:
    """Активные FAQ с флагом быстрой кнопки для виджета на сайте."""
    from supportchat.faq import CHAT_FAQ_LIMIT
    from supportchat.faq import chat_faq_items as _chat_faq_items

    resolved_limit = CHAT_FAQ_LIMIT if limit is None else limit
    return _chat_faq_items(limit=resolved_limit)
