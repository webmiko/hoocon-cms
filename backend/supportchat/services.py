"""Conversation helpers: session web + messenger ingest + staff reply."""

from __future__ import annotations

import logging
import re
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
    ReplyTemplate,
    touch_conversation_message,
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


def start_or_resume_web_conversation(
    request: HttpRequest,
    *,
    display_name: str = "",
    contact_email: str = "",
    page_url: str = "",
) -> Conversation:
    """Create or resume the web Conversation for this browser session."""
    session_id = get_or_create_web_session_id(request)
    page = (page_url or "").strip()[:500]
    with transaction.atomic():
        conv, created = Conversation.objects.get_or_create(
            channel=Channel.WEB,
            external_user_id=session_id,
            defaults={
                "display_name": (display_name or "").strip()[:200],
                "contact_email": (contact_email or "").strip()[:254],
                "page_url": page,
                "status": ConversationStatus.OPEN,
            },
        )
        # Re-lock so concurrent resume/update for the same session does not
        # overwrite display_name/contact_email/status.
        conv = Conversation.objects.select_for_update().get(pk=conv.pk)
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
            if page and page != conv.page_url:
                conv.page_url = page
                updates.append("page_url")
            if conv.status == ConversationStatus.CLOSED:
                _reopen_conversation(conv)
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

    if staff_acknowledgement_pending(conversation):
        from supportchat.tasks import _schedule_escalation_busy_followup

        _schedule_escalation_busy_followup(conversation.pk)
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


def rate_conversation(conversation: Conversation, score: int) -> None:
    """Persist client rating 1–5; requires at least one assistant/staff reply."""
    if not isinstance(score, int) or not 1 <= score <= 5:
        raise SupportChatError("Оценка должна быть от 1 до 5.")
    has_reply = conversation.messages.filter(
        direction__in=(MessageDirection.OUTBOUND, MessageDirection.SYSTEM),
    ).exists()
    if not has_reply:
        raise SupportChatError("Пока нечего оценивать — дождитесь ответа.")
    conversation.rating = score
    conversation.rated_at = timezone.now()
    conversation.save(update_fields=["rating", "rated_at", "updated_at"])
    Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.SYSTEM,
        body=f"Клиент оценил диалог: {score}/5",
        raw_payload={"rating": score},
    )


RATING_CALLBACK_PREFIX = "support_rate:"


def support_rating_callback_payload(conversation_id: int, score: int) -> str:
    """Inline-button payload ``support_rate:<conv>:<1..5>`` (TG/MAX)."""
    return f"{RATING_CALLBACK_PREFIX}{conversation_id}:{score}"


def parse_support_rating_callback(payload: str) -> tuple[int, int] | None:
    """Parse ``support_rate:<conv>:<score>`` → ``(conv_id, score)`` or None."""
    raw = (payload or "").strip()
    if not raw.startswith(RATING_CALLBACK_PREFIX):
        return None
    parts = raw[len(RATING_CALLBACK_PREFIX) :].split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    conv_id, score = int(parts[0]), int(parts[1])
    if not 1 <= score <= 5:
        return None
    return conv_id, score


def support_rating_reply_markup_tg(conversation_id: int) -> dict[str, Any]:
    """Telegram inline keyboard: ⭐1…⭐5 under the rating request."""
    buttons = [
        {
            "text": f"{n} ⭐",
            "callback_data": support_rating_callback_payload(conversation_id, n),
        }
        for n in range(1, 6)
    ]
    return {"inline_keyboard": [buttons]}


def support_rating_attachments_max(conversation_id: int) -> list[dict[str, Any]]:
    """MAX inline keyboard: ⭐1…⭐5 under the rating request."""
    buttons = [
        {
            "type": "callback",
            "text": f"{n} ⭐",
            "payload": support_rating_callback_payload(conversation_id, n),
        }
        for n in range(1, 6)
    ]
    return [{"type": "inline_keyboard", "payload": {"buttons": [buttons]}}]


def request_client_rating(conversation: Conversation) -> None:
    """Enqueue a rating request when a closed dialog has staff replies."""
    if conversation.status != ConversationStatus.CLOSED or conversation.rating is not None:
        return
    conversation_id = conversation.pk

    def _enqueue() -> None:
        from supportchat.tasks import send_rating_request

        send_rating_request.delay(conversation_id)

    transaction.on_commit(_enqueue)


_STAFF_ASSIGN_RE = re.compile(
    r"^(?:@([\w.@+-]+)|/assign\s+@?([\w.@+-]+))\s*$",
    re.IGNORECASE,
)
_STAFF_TEMPLATE_RE = re.compile(r"^/t\s+([\w-]+)\s*$", re.IGNORECASE)
_STAFF_TEMPLATE_LIST = {"/t", "/tpls", "/templates"}


def _staff_user_by_handle(handle: str) -> AbstractBaseUser | None:
    """Active staff user for an ``@handle`` (username, email or first name)."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from accounts.roles import GROUP_ADMIN, GROUP_MANAGER

    h = (handle or "").lstrip("@").strip()
    if not h:
        return None
    return (
        get_user_model()
        .objects.filter(is_active=True, is_staff=True)
        .filter(
            Q(username__iexact=h)
            | Q(email__iexact=h)
            | Q(first_name__iexact=h)
            | Q(username__iregex=rf"^{re.escape(h)}@"),
        )
        .filter(
            Q(groups__name__in=(GROUP_MANAGER, GROUP_ADMIN)) | Q(is_superuser=True),
        )
        .distinct()
        .first()
    )


def submit_staff_reply(
    staff_user: AbstractBaseUser,
    conversation_id: int,
    body: str,
) -> tuple[bool, str]:
    """Staff reply/note/assign/template from any messenger (shared core).

    Commands inside the text: ``/note …`` internal note, ``@handle`` or
    ``/assign …`` reassign, ``/t slug`` canned reply (``/t`` lists slugs).

    Returns:
        (ok, plain-text status for the staff chat).
    """
    from django.contrib.auth.models import PermissionsMixin

    if not isinstance(staff_user, PermissionsMixin) or not staff_user.has_perm(
        "supportchat.change_conversation",
    ):
        logger.warning(
            "staff_reply_denied user=%s conv=%s — missing supportchat.change_conversation",
            getattr(staff_user, "pk", None),
            conversation_id,
        )
        return False, "Недостаточно прав для ответа в поддержке."

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return False, f"Диалог #{conversation_id} не найден."

    text = body.strip()
    if text.lower().startswith("/note"):
        try:
            add_staff_note(conversation, text[5:].strip(), author=staff_user)
        except SupportChatError as exc:
            return False, str(exc)
        return True, f"Заметка сохранена · диалог #{conversation_id} (клиенту не видна)"

    if text.lower() in _STAFF_TEMPLATE_LIST:
        templates = active_reply_templates()
        if not templates:
            return False, "Шаблоны не настроены (Admin → Диалоги поддержки → Шаблоны ответов)."
        lines = "\n".join(f"• /t {tpl.slug} — {tpl.title}" for tpl in templates)
        return True, f"Шаблоны ответов:\n{lines}\n\nИспользование: #{conversation_id} /t код"

    template_match = _STAFF_TEMPLATE_RE.match(text)
    if template_match:
        slug = template_match.group(1)
        template = find_reply_template(slug)
        if template is None:
            return False, f"Шаблон «{slug}» не найден. Список: /t"
        text = template.body

    assign_match = _STAFF_ASSIGN_RE.match(text)
    if assign_match:
        handle = assign_match.group(1) or assign_match.group(2) or ""
        target = _staff_user_by_handle(handle)
        if target is None:
            return False, f"Сотрудник «{handle}» не найден (username/email/имя)."
        assign_conversation(conversation, target, actor=staff_user)
        return True, f"Диалог #{conversation_id} передан: {staff_public_name(target)}"

    try:
        message = add_staff_reply(conversation, text, author=staff_user)
    except SupportChatError as exc:
        return False, str(exc)

    from supportchat.tasks import deliver_outbound_message

    try:
        deliver_outbound_message.delay(message.pk)
    except Exception as exc:
        logger.warning(
            "staff_reply_deliver_enqueue_failed error=%s",
            type(exc).__name__,
        )
        deliver_outbound_message(message.pk)

    label = conversation.display_name or conversation.external_user_id
    channel = conversation.get_channel_display()
    return True, f"Ответ отправлен · диалог #{conversation_id} · {channel} · {label}"


def find_reply_template(slug: str) -> ReplyTemplate | None:
    """Active canned reply by slug (``/t dostavka`` in messengers)."""
    key = (slug or "").strip().lower()
    if not key:
        return None
    return ReplyTemplate.objects.filter(slug__iexact=key, is_active=True).first()


def active_reply_templates() -> list[ReplyTemplate]:
    """Canned replies for Admin composer dropdown / messenger ``/t`` list."""
    return list(ReplyTemplate.objects.filter(is_active=True))


@transaction.atomic
def assign_conversation(
    conversation: Conversation,
    target: AbstractBaseUser | None,
    *,
    actor: AbstractBaseUser | None,
) -> Message:
    """Reassign the dialog to another staff member and log an internal note."""
    conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
    conversation.assignee = target  # type: ignore[assignment]
    conversation.save(update_fields=["assignee", "updated_at"])
    target_label = staff_public_name(target) if target is not None else "—"
    actor_label = staff_public_name(actor)
    return add_staff_note(
        conversation,
        f"{actor_label}: диалог передан → {target_label}",
        author=actor,
    )


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
    mime = (message.attachment_mime or "").strip().lower()
    if mime:
        return mime.startswith("image/")
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
