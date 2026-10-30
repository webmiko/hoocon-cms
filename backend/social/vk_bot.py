"""VK community Callback API: menu commands + support ingest (like MAX bot)."""

from __future__ import annotations

import logging
from typing import Any

from social.copy import clip_text, hours_and_phone_line
from social.max_bot import (
    compose_catalog_reply,
    compose_chatid_reply,
    compose_consultation_reply,
    compose_contacts_text,
    compose_fallback_reply,
    compose_where_reply,
    resolve_menu_action,
)
from social.publishers import PublishResult, publish_vk_dm
from social.vk_bot_handlers import (
    reply_keyboard_for_action,
    send_to_vk_user,
    try_staff_vk_reply,
    vk_message_attachment,
)
from social.vk_client_menu import main_menu_keyboard_vk
from social.vk_community import (
    upload_message_photo,
    vk_community_url,
    vk_community_write_link,
    welcome_dm_photo_path,
)

logger = logging.getLogger("hoocon.social")

_MESSAGE_MAX = 4000

# Re-export for supportchat and tests importing from vk_bot.
__all__ = [
    "compose_vk_welcome_text",
    "handle_vk_callback",
    "send_vk_welcome",
    "vk_community_url",
    "vk_community_write_link",
]


def compose_vk_welcome_text() -> str:
    """Plain welcome for /start, /help and message_allow (VK community, not MAX)."""
    text = (
        "Добро пожаловать в Hoocon!\n\n"
        "HOOCON — электроприводы и арматура для вентиляции и ОВК.\n\n"
        "Кнопки ниже — каталог, заявка, документы, контакты и сообщество VK.\n"
        "Или напишите вопрос — ответим в рабочие дни.\n\n"
        f"Новости и статьи: {vk_community_url()}\n"
        f"Режим ответа: {hours_and_phone_line()}"
    )
    return clip_text(text, _MESSAGE_MAX)


def compose_vk_channel_reply() -> str:
    """Plain-text pointer to the news community (not MAX channel)."""
    return f"Официальное сообщество Hoocon: {vk_community_url()}\n\nНовости, анонсы каталога и статьи по подбору."


def send_vk_welcome(user_key: str) -> PublishResult:
    """Welcome DM with optional cover photo and inline menu."""
    from sitesettings.models import SiteSettings

    attachment: str | None = None
    gid = (SiteSettings.load().vk_group_id or "").strip().lstrip("-")
    photo = welcome_dm_photo_path()
    if gid.isdigit() and photo is not None:
        uploaded, up_err = upload_message_photo(gid, user_key, photo)
        if uploaded:
            attachment = uploaded
        elif up_err:
            logger.warning("vk_welcome_photo_skipped reason=%s", up_err[:120])

    return publish_vk_dm(
        user_id=user_key,
        text=compose_vk_welcome_text(),
        keyboard=main_menu_keyboard_vk(),
        attachment=attachment,
    )


def _compose_reply_for_action(action: str, user_key: str) -> str:
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


def _handle_message_allow(event: dict[str, Any]) -> PublishResult | None:
    obj = event.get("object")
    if not isinstance(obj, dict):
        return None
    user_id = obj.get("user_id")
    if user_id is None:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    if uid <= 0:
        return None
    return send_vk_welcome(str(uid))


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
        if action in {"start", "help"}:
            return send_vk_welcome(user_key)
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
    if event_type == "message_allow":
        return _handle_message_allow(event)
    if event_type == "message_event":
        from social.vk_bot_handlers import handle_message_event

        return handle_message_event(event)
    return None
