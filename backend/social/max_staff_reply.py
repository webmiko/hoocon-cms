"""Staff support replies from personal MAX chat (#ID text or /reply ID text)."""

from __future__ import annotations

import re
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.cache import cache
from django.db.models import Q

from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult, publish_max

User = get_user_model()

_STAFF_REPLY_CALLBACK_PREFIX = "staff_reply:"
_PENDING_REPLY_CACHE_TTL = 30 * 60
_STAFF_REPLY_HASH_RE = re.compile(r"^#(\d+)\s+(.+)$", re.DOTALL)
_STAFF_REPLY_CMD_RE = re.compile(
    r"^/reply(?:\s+(\d+)\s+(.+))?\s*$",
    re.DOTALL | re.IGNORECASE,
)


def parse_staff_reply_text(text: str) -> tuple[int, str] | None:
    """Parse ``#42 ответ`` or ``/reply 42 ответ``; return (conversation_id, body)."""
    raw = (text or "").strip()
    if not raw:
        return None
    match = _STAFF_REPLY_HASH_RE.match(raw)
    if match:
        return int(match.group(1)), match.group(2).strip()
    match = _STAFF_REPLY_CMD_RE.match(raw)
    if match and match.group(1) and match.group(2):
        return int(match.group(1)), match.group(2).strip()
    return None


def staff_user_for_max_user_id(max_user_id: str) -> AbstractBaseUser | None:
    """Active staff with this MAX user_id (manager or superuser, alerts on)."""
    uid = (max_user_id or "").strip()
    if not uid:
        return None
    return (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            max_profile__max_user_id=uid,
            max_profile__max_alerts_enabled=True,
        )
        .filter(Q(groups__name=GROUP_MANAGER) | Q(is_superuser=True))
        .distinct()
        .first()
    )


def staff_reply_callback_payload(conversation_id: int) -> str:
    """Inline callback payload for the «Ответить» button on staff alerts."""
    return f"{_STAFF_REPLY_CALLBACK_PREFIX}{conversation_id}"


def parse_staff_reply_callback_payload(payload: str) -> int | None:
    """Return conversation id from callback payload or None."""
    raw = (payload or "").strip()
    if not raw.startswith(_STAFF_REPLY_CALLBACK_PREFIX):
        return None
    suffix = raw[len(_STAFF_REPLY_CALLBACK_PREFIX) :].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def _pending_reply_cache_key(max_user_id: str) -> str:
    return f"max_staff_reply_pending:{(max_user_id or '').strip()}"


def set_pending_staff_reply(max_user_id: str, conversation_id: int) -> None:
    """Remember which support dialog the manager is replying to from MAX."""
    uid = (max_user_id or "").strip()
    if not uid:
        return
    cache.set(_pending_reply_cache_key(uid), conversation_id, timeout=_PENDING_REPLY_CACHE_TTL)


def get_pending_staff_reply(max_user_id: str) -> int | None:
    """Return pending conversation id for this staff MAX user, if any."""
    uid = (max_user_id or "").strip()
    if not uid:
        return None
    value = cache.get(_pending_reply_cache_key(uid))
    if value is None:
        return None
    return int(value)


def clear_pending_staff_reply(max_user_id: str) -> None:
    """Drop pending reply mode (menu command or explicit #ID reply)."""
    uid = (max_user_id or "").strip()
    if uid:
        cache.delete(_pending_reply_cache_key(uid))


def compose_staff_reply_prompt(conversation_id: int) -> str:
    """Prompt after the manager taps «Ответить» on a staff alert."""
    return f"Диалог #{conversation_id} — напишите ответ одним сообщением.\nНомер подставлять не нужно."


def staff_support_alert_attachments(conversation_id: int) -> list[dict[str, Any]]:
    """Inline keyboard under staff support alerts: reply + Admin link."""
    from django.conf import settings

    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    admin_url = f"{site}/admin/supportchat/conversation/{conversation_id}/change/"
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [
                        {
                            "type": "callback",
                            "text": "Ответить",
                            "payload": staff_reply_callback_payload(conversation_id),
                        },
                        {
                            "type": "link",
                            "text": "Admin",
                            "url": admin_url,
                        },
                    ],
                ],
            },
        },
    ]


def compose_staff_reply_help() -> str:
    """Hint for managers replying to clients from personal MAX."""
    return (
        "Ответ клиенту из MAX:\n"
        "• кнопка «Ответить» под уведомлением — затем текст ответа\n"
        "• #42 ваш текст — ответ в диалог №42\n"
        "• /reply 42 ваш текст — то же\n\n"
        "/chatid — ваш user_id для Admin."
    )


def compose_staff_account_notice() -> str:
    """Explain why a manager's free text did not open a support thread."""
    return (
        "Ваш MAX привязан как сотрудник — обычные сообщения боту "
        "не попадают в поддержку и не видны в Admin.\n\n"
        + compose_staff_reply_help()
        + "\n\nТест клиентского чата — с другого MAX-аккаунта."
    )


def staff_reply_hint(conversation_id: int) -> str:
    """One-line instruction appended to staff support alerts."""
    return f"Ответить: кнопка ниже или #{conversation_id} ваш текст"


def submit_staff_reply_from_max(
    staff_user: AbstractBaseUser,
    conversation_id: int,
    body: str,
) -> tuple[bool, str]:
    """Store staff reply and enqueue delivery to the client's channel.

    Returns:
        (ok, plain-text status for the staff MAX chat).
    """
    from supportchat.models import Conversation
    from supportchat.services import SupportChatError, add_staff_reply

    if not isinstance(staff_user, PermissionsMixin) or not staff_user.has_perm(
        "supportchat.change_conversation",
    ):
        return False, "Недостаточно прав для ответа в поддержке."

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return False, f"Диалог #{conversation_id} не найден."

    try:
        message = add_staff_reply(conversation, body, author=staff_user)
    except SupportChatError as exc:
        return False, str(exc)

    from supportchat.tasks import deliver_outbound_message

    try:
        deliver_outbound_message.delay(message.pk)
    except Exception:
        deliver_outbound_message(message.pk)

    label = conversation.display_name or conversation.external_user_id
    channel = conversation.get_channel_display()
    return True, f"Ответ отправлен · диалог #{conversation_id} · {channel} · {label}"


def publish_staff_max_text(user_id: str, text: str) -> PublishResult:
    """Send status text to staff user's MAX dialog."""
    return publish_max(user_id=user_id, text=text)
