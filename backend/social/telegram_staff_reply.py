"""Staff support replies from personal Telegram chat (#ID text, «Ответить» button)."""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.db.models import Q

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER

User = get_user_model()
logger = logging.getLogger(__name__)

_PENDING_REPLY_CACHE_TTL = 30 * 60
_SUPPORT_ALERT_MID_TTL = 7 * 24 * 60 * 60


def staff_reply_callback_data(conversation_id: int) -> str:
    """Inline callback_data for the «Ответить» button on staff alerts."""
    return f"staff_reply:{conversation_id}"


def staff_note_callback_data(conversation_id: int) -> str:
    """Inline callback_data for the «📝 Заметка» button."""
    return f"staff_note:{conversation_id}"


def staff_assign_callback_data(conversation_id: int) -> str:
    """Inline callback_data for the «🔀 Передать» button (opens picker)."""
    return f"staff_assign:{conversation_id}"


def staff_assign_to_callback_data(conversation_id: int, user_id: int) -> str:
    """Picker button: transfer the dialog to this staff user."""
    return f"staff_assign_to:{conversation_id}:{user_id}"


def parse_staff_reply_callback_data(data: str) -> int | None:
    """Return conversation id from callback_data or None."""
    raw = (data or "").strip()
    if not raw.startswith("staff_reply:"):
        return None
    suffix = raw[len("staff_reply:") :].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def parse_staff_alert_callback(data: str) -> tuple[str, int, int | None] | None:
    """Parse staff alert callback_data → ``(action, conv_id, target_user_id)``.

    ``assign_to`` must be tried before ``assign`` (shared prefix).
    """
    raw = (data or "").strip()
    for action, prefix in (
        ("assign_to", "staff_assign_to:"),
        ("reply", "staff_reply:"),
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


def staff_user_for_telegram_chat_id(chat_id: str) -> AbstractBaseUser | None:
    """Active staff with this Telegram chat_id (manager or superuser, alerts on).

    ``telegram_chat_id`` is not unique on StaffTelegramProfile — when several
    accounts share it, prefer the one that can actually answer in support chat.
    """
    cid = (chat_id or "").strip()
    if not cid:
        return None
    candidates = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            telegram_profile__telegram_chat_id=cid,
            telegram_profile__telegram_alerts_enabled=True,
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


def _pending_reply_cache_key(chat_id: str) -> str:
    return f"tg_staff_reply_pending:{(chat_id or '').strip()}"


def set_pending_staff_reply(chat_id: str, conversation_id: int, mode: str = "reply") -> None:
    """Remember which support dialog the manager is replying to from Telegram.

    ``mode`` is ``reply`` (default) or ``note`` — next text becomes a note.
    """
    cid = (chat_id or "").strip()
    if not cid:
        return
    cache.set(
        _pending_reply_cache_key(cid),
        {"conv": conversation_id, "mode": mode},
        timeout=_PENDING_REPLY_CACHE_TTL,
    )


def get_pending_staff_reply(chat_id: str) -> tuple[int, str] | None:
    """Return ``(conversation_id, mode)`` pending for this staff chat, if any."""
    cid = (chat_id or "").strip()
    if not cid:
        return None
    value = cache.get(_pending_reply_cache_key(cid))
    if isinstance(value, dict):
        return int(value["conv"]), str(value.get("mode") or "reply")
    if value is not None:  # legacy int payload
        return int(value), "reply"
    return None


def clear_pending_staff_reply(chat_id: str) -> None:
    """Drop pending reply mode."""
    cid = (chat_id or "").strip()
    if cid:
        cache.delete(_pending_reply_cache_key(cid))


def _alert_mid_cache_key(conversation_id: int, chat_id: str) -> str:
    cid = (chat_id or "").strip()
    return f"tg-support-alert-mid:{conversation_id}:{cid}"


def store_support_alert_message_id(
    conversation_id: int,
    chat_id: str,
    message_id: str,
    text: str,
) -> None:
    """Remember a staff alert's message_id so its keyboard can be retired."""
    cid = (chat_id or "").strip()
    mid = (message_id or "").strip()
    if not cid or not mid:
        return
    cache.set(
        _alert_mid_cache_key(conversation_id, cid),
        {"message_id": mid, "text": text or ""},
        timeout=_SUPPORT_ALERT_MID_TTL,
    )


def load_support_alert_message_id(
    conversation_id: int,
    chat_id: str,
) -> dict[str, str] | None:
    """Return ``{"message_id", "text"}`` of the alert sent to this staff user."""
    cid = (chat_id or "").strip()
    if not cid:
        return None
    value = cache.get(_alert_mid_cache_key(conversation_id, cid))
    return value if isinstance(value, dict) else None


def staff_support_alert_reply_markup(conversation_id: int) -> dict[str, Any]:
    """Inline keyboard under staff support alerts: reply + Admin link."""
    from django.conf import settings

    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    admin_url = f"{site}/admin/supportchat/conversation/{conversation_id}/change/"
    return {
        "inline_keyboard": [
            [
                {
                    "text": "Ответить",
                    "callback_data": staff_reply_callback_data(conversation_id),
                },
                {
                    "text": "📝 Заметка",
                    "callback_data": staff_note_callback_data(conversation_id),
                },
                {
                    "text": "🔀 Передать",
                    "callback_data": staff_assign_callback_data(conversation_id),
                },
                {"text": "Admin", "url": admin_url},
            ],
        ],
    }


def staff_transfer_keyboard_markup(
    conversation_id: int,
    *,
    exclude_pk: int | None = None,
) -> dict[str, Any]:
    """Inline keyboard listing colleagues the dialog can be handed to."""
    from supportchat.services import staff_public_name, staff_transfer_candidates

    buttons = [
        [
            {
                "text": staff_public_name(user),
                "callback_data": staff_assign_to_callback_data(conversation_id, user.pk),
            },
        ]
        for user in staff_transfer_candidates(exclude_pk=exclude_pk)
    ]
    return {"inline_keyboard": buttons}


def compose_staff_reply_prompt(conversation_id: int) -> str:
    """Prompt after the manager taps «Ответить» on a staff alert."""
    return f"Диалог #{conversation_id} — напишите ответ одним сообщением.\nНомер подставлять не нужно."


def compose_staff_note_prompt(conversation_id: int) -> str:
    """Prompt after the manager taps «📝 Заметка» on a staff alert."""
    return f"Диалог #{conversation_id} — следующее сообщение станет внутренней заметкой.\nКлиент её не увидит."


def compose_staff_reply_help() -> str:
    """Hint for managers replying to clients from personal Telegram."""
    return (
        "Ответ клиенту из Telegram:\n"
        "• кнопка «Ответить» под уведомлением — затем текст ответа\n"
        "• #42 ваш текст — ответ в диалог №42\n"
        "• /reply 42 ваш текст — то же\n\n"
        "• #42 /note текст — внутренняя заметка (клиенту не видна)\n"
        "• #42 @username — передать диалог коллеге\n"
        "• #42 /t код — шаблонный ответ (список: #42 /t)"
    )


def compose_staff_account_notice() -> str:
    """Explain why a manager's free text did not open a support thread."""
    return (
        "Ваш Telegram привязан как сотрудник — обычные сообщения боту "
        "не попадают в поддержку и не видны в Admin.\n\n" + compose_staff_reply_help()
    )


def submit_staff_reply_from_telegram(
    staff_user: AbstractBaseUser,
    conversation_id: int,
    body: str,
) -> tuple[bool, str]:
    """Store staff reply and enqueue delivery to the client's channel."""
    from supportchat.services import submit_staff_reply

    return submit_staff_reply(staff_user, conversation_id, body)
