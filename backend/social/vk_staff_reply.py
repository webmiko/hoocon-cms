"""Staff support replies from personal VK chat (mirror of MAX staff flow)."""

from __future__ import annotations

import json
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.core.cache import cache
from django.db.models import Q

from accounts.roles import GROUP_ADMIN, GROUP_MANAGER
from social.max_staff_reply import (
    compose_staff_account_notice as _max_compose_staff_account_notice,
)
from social.max_staff_reply import (
    compose_staff_reply_help as _max_compose_staff_reply_help,
)
from social.max_staff_reply import (
    staff_assign_callback_payload,
    staff_assign_to_callback_payload,
    staff_note_callback_payload,
    staff_reply_callback_payload,
    submit_staff_reply_from_max,
)
from social.publishers import PublishResult, publish_vk_dm
from social.vk_keyboard import vk_inline_keyboard

User = get_user_model()
logger = logging.getLogger(__name__)

_PENDING_REPLY_CACHE_TTL = 30 * 60
_SUPPORT_ALERT_MID_TTL = 7 * 24 * 60 * 60


def staff_user_for_vk_user_id(vk_user_id: str) -> AbstractBaseUser | None:
    """Active staff with this VK user id (manager or superuser, alerts on)."""
    uid = (vk_user_id or "").strip()
    if not uid:
        return None
    candidates = (
        User.objects.filter(
            is_active=True,
            is_staff=True,
            vk_profile__vk_user_id=uid,
            vk_profile__vk_alerts_enabled=True,
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


def _pending_reply_cache_key(vk_user_id: str) -> str:
    return f"vk_staff_reply_pending:{(vk_user_id or '').strip()}"


def set_pending_staff_reply(vk_user_id: str, conversation_id: int, mode: str = "reply") -> None:
    uid = (vk_user_id or "").strip()
    if not uid:
        return
    cache.set(
        _pending_reply_cache_key(uid),
        {"conv": conversation_id, "mode": mode},
        timeout=_PENDING_REPLY_CACHE_TTL,
    )


def get_pending_staff_reply(vk_user_id: str) -> tuple[int, str] | None:
    uid = (vk_user_id or "").strip()
    if not uid:
        return None
    value = cache.get(_pending_reply_cache_key(uid))
    if isinstance(value, dict):
        return int(value["conv"]), str(value.get("mode") or "reply")
    if value is not None:
        return int(value), "reply"
    return None


def clear_pending_staff_reply(vk_user_id: str) -> None:
    uid = (vk_user_id or "").strip()
    if uid:
        cache.delete(_pending_reply_cache_key(uid))


def _alert_mid_cache_key(conversation_id: int, vk_user_id: str) -> str:
    uid = (vk_user_id or "").strip()
    return f"vk-support-alert-mid:{conversation_id}:{uid}"


def store_support_alert_mid(
    conversation_id: int,
    vk_user_id: str,
    cmid: str,
    text: str,
) -> None:
    uid = (vk_user_id or "").strip()
    mid = (cmid or "").strip()
    if not uid or not mid:
        return
    cache.set(
        _alert_mid_cache_key(conversation_id, uid),
        {"cmid": mid, "text": text or ""},
        timeout=_SUPPORT_ALERT_MID_TTL,
    )


def load_support_alert_mid(conversation_id: int, vk_user_id: str) -> dict[str, str] | None:
    uid = (vk_user_id or "").strip()
    if not uid:
        return None
    value = cache.get(_alert_mid_cache_key(conversation_id, uid))
    return value if isinstance(value, dict) else None


def staff_support_alert_keyboard(conversation_id: int) -> str:
    """Inline keyboard JSON for staff support alerts."""
    from django.conf import settings

    site = getattr(settings, "SITE_URL", "https://hoocon.ru").rstrip("/")
    admin_url = f"{site}/admin/supportchat/conversation/{conversation_id}/change/"
    return vk_inline_keyboard(
        [
            [
                {"type": "callback", "text": "Ответить", "payload": staff_reply_callback_payload(conversation_id)},
                {"type": "callback", "text": "📝 Заметка", "payload": staff_note_callback_payload(conversation_id)},
            ],
            [
                {"type": "callback", "text": "🔀 Передать", "payload": staff_assign_callback_payload(conversation_id)},
                {"type": "link", "text": "Admin", "url": admin_url},
            ],
        ],
    )


def staff_transfer_keyboard(conversation_id: int, *, exclude_pk: int | None = None) -> str:
    from supportchat.presentation import staff_public_name
    from supportchat.staff_actions import staff_transfer_candidates

    rows = [
        [
            {
                "type": "callback",
                "text": staff_public_name(user),
                "payload": staff_assign_to_callback_payload(conversation_id, user.pk),
            },
        ]
        for user in staff_transfer_candidates(exclude_pk=exclude_pk)
    ]
    return vk_inline_keyboard(rows)


def compose_staff_reply_help() -> str:
    return _max_compose_staff_reply_help().replace("MAX", "VK").replace("user_id", "VK user_id")


def compose_staff_account_notice() -> str:
    return _max_compose_staff_account_notice().replace("MAX", "VK").replace("MAX-аккаунта", "VK-аккаунта")


def submit_staff_reply_from_vk(
    staff_user: AbstractBaseUser,
    conversation_id: int,
    body: str,
) -> tuple[bool, str]:
    return submit_staff_reply_from_max(staff_user, conversation_id, body)


def publish_staff_vk_text(user_id: str, text: str, *, keyboard: str | None = None) -> PublishResult:
    return publish_vk_dm(user_id=user_id, text=text, keyboard=keyboard)


def answer_vk_message_event(
    *,
    event_id: int,
    user_id: int,
    peer_id: int,
    text: str,
) -> None:
    from social.publishers import vk_api_call

    event_data = json.dumps({"type": "show_snackbar", "text": text[:90]}, ensure_ascii=False)
    vk_api_call(
        "messages.sendMessageEventAnswer",
        {
            "event_id": event_id,
            "user_id": user_id,
            "peer_id": peer_id,
            "event_data": event_data,
        },
    )
