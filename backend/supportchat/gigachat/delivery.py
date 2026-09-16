"""Deliver AI system messages to messenger channels."""

from __future__ import annotations

import html
import logging

from supportchat.gigachat.site_links import expand_site_links_for_messenger
from supportchat.models import Channel, Conversation, Message

logger = logging.getLogger("hoocon.supportchat.gigachat")


def _messenger_text(body: str) -> str:
    return expand_site_links_for_messenger(body)


def deliver_ai_message(conversation: Conversation, message: Message) -> None:
    """Push AI reply to Telegram/MAX; web clients poll the thread."""
    if conversation.channel == Channel.WEB:
        return
    outbound = _messenger_text(message.body)
    if conversation.channel == Channel.TELEGRAM:
        from social.publishers import publish_telegram
        from social.telegram_bot import main_menu_keyboard

        result = publish_telegram(
            chat_id=conversation.external_user_id,
            text=html.escape(outbound),
            reply_markup=main_menu_keyboard(),
        )
        if not result.ok:
            logger.warning(
                "gigachat_tg_delivery_failed conversation_id=%s err=%s",
                conversation.pk,
                (result.error or "")[:120],
            )
        return
    if conversation.channel == Channel.MAX:
        from social.publishers import publish_max

        result = publish_max(
            user_id=conversation.external_user_id,
            text=outbound,
        )
        if not result.ok:
            logger.warning(
                "gigachat_max_delivery_failed conversation_id=%s err=%s",
                conversation.pk,
                (result.error or "")[:120],
            )
