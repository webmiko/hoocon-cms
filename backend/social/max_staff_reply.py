"""Staff support replies from personal MAX chat (#ID text or /reply ID text)."""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db.models import Q

from accounts.roles import GROUP_MANAGER
from social.publishers import PublishResult, publish_max

User = get_user_model()

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


def compose_staff_reply_help() -> str:
    """Hint for managers replying to clients from personal MAX."""
    return (
        "Ответ клиенту из MAX:\n"
        "• #42 ваш текст — ответ в диалог №42\n"
        "• /reply 42 ваш текст — то же\n\n"
        "Номер диалога — в уведомлении о новом сообщении.\n"
        "/chatid — ваш user_id для Admin."
    )


def staff_reply_hint(conversation_id: int) -> str:
    """One-line instruction appended to staff support alerts."""
    return f"Ответить из MAX: #{conversation_id} ваш текст"


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
