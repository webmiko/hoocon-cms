"""Staff support replies from personal MAX chat (#ID text or /reply ID text)."""

from __future__ import annotations

import logging
import re
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.db.models import Q

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from social.publishers import PublishResult, publish_max

User = get_user_model()
logger = logging.getLogger(__name__)

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
    """Active staff with this MAX user_id (manager or superuser, alerts on).

    ``max_user_id`` is not unique on StaffMaxProfile — when several accounts
    share it, prefer the one that can actually answer in support chat.
    """
    uid = (max_user_id or "").strip()
    if not uid:
        return None
    candidates = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            max_profile__max_user_id=uid,
            max_profile__max_alerts_enabled=True,
        )
        .filter(
            Q(groups__name__in=(GROUP_MANAGER, GROUP_ADMIN)) | Q(is_superuser=True),
        )
        .distinct()
    )
    fallback = None
    for candidate in candidates:
        if fallback is None:
            fallback = candidate
        if candidate.has_perm("supportchat.change_conversation"):
            return candidate
    return fallback


def staff_reply_callback_payload(conversation_id: int) -> str:
    """Inline callback payload for the «Ответить» button on staff alerts."""
    return f"{_STAFF_REPLY_CALLBACK_PREFIX}{conversation_id}"


def staff_note_callback_payload(conversation_id: int) -> str:
    """Inline callback payload for the «📝 Заметка» button."""
    return f"staff_note:{conversation_id}"


def staff_assign_callback_payload(conversation_id: int) -> str:
    """Inline callback payload for the «🔀 Передать» button (opens picker)."""
    return f"staff_assign:{conversation_id}"


def staff_assign_to_callback_payload(conversation_id: int, user_id: int) -> str:
    """Picker button payload: transfer the dialog to this staff user."""
    return f"staff_assign_to:{conversation_id}:{user_id}"


def parse_staff_reply_callback_payload(payload: str) -> int | None:
    """Return conversation id from callback payload or None."""
    raw = (payload or "").strip()
    if not raw.startswith(_STAFF_REPLY_CALLBACK_PREFIX):
        return None
    suffix = raw[len(_STAFF_REPLY_CALLBACK_PREFIX) :].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def parse_staff_alert_callback(payload: str) -> tuple[str, int, int | None] | None:
    """Parse staff alert payload → ``(action, conv_id, target_user_id)``.

    ``assign_to`` must be tried before ``assign`` (shared prefix).
    """
    raw = (payload or "").strip()
    for action, prefix in (
        ("assign_to", "staff_assign_to:"),
        ("reply", _STAFF_REPLY_CALLBACK_PREFIX),
        ("note", "staff_note:"),
        ("assign", "staff_assign:"),
    ):
        if not raw.startswith(prefix):
            continue
        rest = raw[len(prefix) :]
        if action == "assign_to":
            conv_part, _, user_part = rest.partition(":")
            if conv_part.strip().isdigit() and user_part.strip().isdigit():
                return action, int(conv_part), int(user_part)
            return None
        if rest.strip().isdigit():
            return action, int(rest), None
        return None
    return None


def _pending_reply_cache_key(max_user_id: str) -> str:
    return f"max_staff_reply_pending:{(max_user_id or '').strip()}"


def set_pending_staff_reply(max_user_id: str, conversation_id: int, mode: str = "reply") -> None:
    """Remember which support dialog the manager is replying to from MAX.

    ``mode`` is ``reply`` (default) or ``note`` — next text becomes a note.
    """
    uid = (max_user_id or "").strip()
    if not uid:
        return
    cache.set(
        _pending_reply_cache_key(uid),
        {"conv": conversation_id, "mode": mode},
        timeout=_PENDING_REPLY_CACHE_TTL,
    )


def get_pending_staff_reply(max_user_id: str) -> tuple[int, str] | None:
    """Return ``(conversation_id, mode)`` pending for this staff MAX user, if any."""
    uid = (max_user_id or "").strip()
    if not uid:
        return None
    value = cache.get(_pending_reply_cache_key(uid))
    if isinstance(value, dict):
        return int(value["conv"]), str(value.get("mode") or "reply")
    if value is not None:  # legacy int payload
        return int(value), "reply"
    return None


def clear_pending_staff_reply(max_user_id: str) -> None:
    """Drop pending reply mode (menu command or explicit #ID reply)."""
    uid = (max_user_id or "").strip()
    if uid:
        cache.delete(_pending_reply_cache_key(uid))


def compose_staff_reply_prompt(conversation_id: int) -> str:
    """Prompt after the manager taps «Ответить» on a staff alert."""
    return f"Диалог #{conversation_id} — напишите ответ одним сообщением.\nНомер подставлять не нужно."


def compose_staff_note_prompt(conversation_id: int) -> str:
    """Prompt after the manager taps «📝 Заметка» on a staff alert."""
    return f"Диалог #{conversation_id} — следующее сообщение станет внутренней заметкой.\nКлиент её не увидит."


_SUPPORT_ALERT_MID_TTL = 7 * 24 * 60 * 60


def _alert_mid_cache_key(conversation_id: int, max_user_id: str) -> str:
    uid = (max_user_id or "").strip()
    return f"max-support-alert-mid:{conversation_id}:{uid}"


def store_support_alert_mid(
    conversation_id: int,
    max_user_id: str,
    mid: str,
    text: str,
) -> None:
    """Remember a staff alert's message mid so it can be edited later."""
    uid = (max_user_id or "").strip()
    mid = (mid or "").strip()
    if not uid or not mid:
        return
    cache.set(
        _alert_mid_cache_key(conversation_id, uid),
        {"mid": mid, "text": text or ""},
        timeout=_SUPPORT_ALERT_MID_TTL,
    )


def load_support_alert_mid(conversation_id: int, max_user_id: str) -> dict[str, str] | None:
    """Return ``{"mid", "text"}`` of the alert sent to this staff user."""
    uid = (max_user_id or "").strip()
    if not uid:
        return None
    value = cache.get(_alert_mid_cache_key(conversation_id, uid))
    return value if isinstance(value, dict) else None


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
                            "type": "callback",
                            "text": "📝 Заметка",
                            "payload": staff_note_callback_payload(conversation_id),
                        },
                    ],
                    [
                        {
                            "type": "callback",
                            "text": "🔀 Передать",
                            "payload": staff_assign_callback_payload(conversation_id),
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


def staff_transfer_keyboard_attachments(
    conversation_id: int,
    *,
    exclude_pk: int | None = None,
) -> list[dict[str, Any]]:
    """Inline keyboard message attachment listing colleagues for transfer."""
    from supportchat.presentation import staff_public_name
    from supportchat.staff_actions import staff_transfer_candidates

    buttons = [
        [
            {
                "type": "callback",
                "text": staff_public_name(user),
                "payload": staff_assign_to_callback_payload(conversation_id, user.pk),
            },
        ]
        for user in staff_transfer_candidates(exclude_pk=exclude_pk)
    ]
    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def compose_staff_reply_help() -> str:
    """Hint for managers replying to clients from personal MAX."""
    return (
        "Ответ клиенту из MAX:\n"
        "• кнопка «Ответить» под уведомлением — затем текст ответа\n"
        "• #42 ваш текст — ответ в диалог №42\n"
        "• /reply 42 ваш текст — то же\n\n"
        "• #42 /note текст — внутренняя заметка (клиенту не видна)\n"
        "• #42 @username — передать диалог коллеге\n"
        "• #42 /t код — шаблонный ответ (список: #42 /t)\n\n"
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
    from supportchat.staff_actions import submit_staff_reply

    return submit_staff_reply(staff_user, conversation_id, body)


def publish_staff_max_text(user_id: str, text: str) -> PublishResult:
    """Send status text to staff user's MAX dialog."""
    return publish_max(user_id=user_id, text=text)
