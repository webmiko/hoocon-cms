"""VK community Callback API: menu commands + support ingest (like MAX bot)."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from social.max_bot import (
    compose_catalog_reply,
    compose_chatid_reply,
    compose_consultation_reply,
    compose_contacts_text,
    compose_fallback_reply,
    compose_welcome_text,
    compose_where_reply,
    resolve_menu_action,
)
from social.publishers import PublishResult
from social.vk_bot_handlers import (
    reply_keyboard_for_action,
    send_to_vk_user,
    try_staff_vk_reply,
    vk_message_attachment,
)
from social.vk_client_menu import main_menu_keyboard_vk

logger = logging.getLogger("hoocon.social")


def vk_community_screen_name() -> str:
    """Public community slug for vk.me deep links."""
    raw = getattr(settings, "VK_COMMUNITY_SCREEN_NAME", "hoocon_russia").strip().lstrip("@")
    return raw or "hoocon_russia"


def vk_community_url() -> str:
    """HTTPS URL of the official VK community."""
    return f"https://vk.ru/{vk_community_screen_name()}"


def vk_community_write_link() -> str:
    """Open 1:1 chat with the community (messages)."""
    return f"https://vk.me/{vk_community_screen_name()}"


def compose_vk_channel_reply() -> str:
    """Plain-text pointer to the news community (not MAX channel)."""
    return f"Официальное сообщество Hoocon: {vk_community_url()}\n\nНовости, анонсы каталога и статьи по подбору."


def _compose_reply_for_action(action: str, user_key: str) -> str:
    if action in {"start", "help"}:
        return compose_welcome_text()
    if action in {"contacts", "contact"}:
        return compose_contacts_text()
    if action == "catalog":
        return compose_catalog_reply()
    if action == "consultation":
        return compose_consultation_reply()
    if action in {"where", "gdekupit", "where_to_buy"}:
        return compose_where_reply()
    if action == "channel":
        return compose_vk_channel_reply()
    if action == "chatid":
        return compose_chatid_reply(user_key)
    return compose_fallback_reply()


def _display_name_from_message(message: dict[str, Any]) -> str:
    title = (message.get("title") or "").strip()
    if title:
        return title[:200]
    return "Клиент VK"


def _message_text(message: dict[str, Any]) -> str:
    return (message.get("text") or "").strip()


def _message_external_id(message: dict[str, Any]) -> str:
    mid = message.get("id")
    if mid is not None:
        return str(mid)
    return str(message.get("date") or "")


def _ingest_support_text(
    *,
    user_id: str,
    text: str,
    message: dict[str, Any],
    display_name: str,
) -> PublishResult | None:
    from supportchat.models import Channel
    from supportchat.services import (
        SupportChatError,
        add_inbound_message,
        get_or_create_messenger_conversation,
    )

    external_message_id = _message_external_id(message)
    try:
        conversation = get_or_create_messenger_conversation(
            Channel.VK,
            user_id,
            display_name=display_name,
        )
        attachment = vk_message_attachment(message)
        _inbound, auto = add_inbound_message(
            conversation,
            text,
            external_message_id=external_message_id,
            raw_payload={"vk_message_id": external_message_id},
            display_name=display_name,
            attachment=attachment[0] if attachment else None,
            attachment_name=attachment[1] if attachment else "",
            attachment_mime=attachment[2] if attachment else "",
        )
    except SupportChatError as exc:
        logger.warning(
            "vk_support_ingest_rejected user_id=%s reason=%s",
            user_id,
            str(exc)[:200],
        )
        return None

    if auto is not None:
        return send_to_vk_user(user_id, auto.body, keyboard=main_menu_keyboard_vk())
    return None


def _handle_message_new(event: dict[str, Any]) -> PublishResult | None:
    obj = event.get("object")
    if not isinstance(obj, dict):
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    if message.get("out") in (1, "1", True):
        return None
    from_id = message.get("from_id")
    if from_id is None:
        return None
    try:
        user_id_int = int(from_id)
    except (TypeError, ValueError):
        return None
    if user_id_int <= 0:
        return None
    user_key = str(user_id_int)
    text = _message_text(message)
    if not text and vk_message_attachment(message) is None:
        return None
    if not text:
        text = ""

    staff_reply = try_staff_vk_reply(user_key, text)
    if staff_reply is not None:
        return staff_reply

    display_name = _display_name_from_message(message)
    action = resolve_menu_action(text)
    if action is not None:
        reply = _compose_reply_for_action(action, user_key)
        return send_to_vk_user(user_key, reply, keyboard=reply_keyboard_for_action(action))

    return _ingest_support_text(
        user_id=user_key,
        text=text,
        message=message,
        display_name=display_name,
    )


def handle_vk_callback(event: dict[str, Any]) -> PublishResult | None:
    """Dispatch one VK Callback API event (except ``confirmation``)."""
    event_type = (event.get("type") or "").strip()
    if event_type == "message_new":
        return _handle_message_new(event)
    if event_type == "message_event":
        from social.vk_bot_handlers import handle_message_event

        return handle_message_event(event)
    return None
