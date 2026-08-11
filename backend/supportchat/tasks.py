"""Celery tasks for support chat outbound delivery."""

from __future__ import annotations

import html
from typing import Any

from celery import shared_task

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.supportchat")


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def deliver_outbound_message(self: Any, message_id: int) -> str:
    """Deliver staff reply to the originating channel (Telegram for now)."""
    from supportchat.models import Channel, Message, MessageDirection

    try:
        msg = Message.objects.select_related("conversation").get(pk=message_id)
    except Message.DoesNotExist:
        return "missing"

    if msg.direction != MessageDirection.OUTBOUND:
        return "skip_not_outbound"

    conversation = msg.conversation
    if conversation.channel == Channel.WEB:
        return "web_poll"
    if conversation.channel == Channel.TELEGRAM:
        # Idempotent: avoid duplicate TG sends on Celery retry after success.
        if (msg.external_message_id or "").strip():
            return "already_delivered"
        from social.publishers import publish_telegram

        result = publish_telegram(
            chat_id=conversation.external_user_id,
            text=html.escape(msg.body),
        )
        if result.skipped:
            logger.warning("support_tg_outbound_skipped message_id=%s", message_id)
            return "skipped"
        if not result.ok:
            logger.warning(
                "support_tg_outbound_failed message_id=%s err=%s",
                message_id,
                result.error[:120],
            )
            raise self.retry(exc=RuntimeError(result.error or "telegram_failed"))
        if result.external_id and not msg.external_message_id:
            msg.external_message_id = result.external_id
            msg.save(update_fields=["external_message_id"])
        return "telegram_ok"
    logger.info(
        "support_outbound_channel_pending channel=%s message_id=%s",
        conversation.channel,
        message_id,
    )
    return "pending_channel"
