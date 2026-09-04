"""Celery tasks for support chat outbound delivery and staff email."""

from __future__ import annotations

import html
from typing import Any

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from config.logging_utils import setup_logger

logger = setup_logger("hoocon.supportchat")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_support_first_inbound_notification(
    self: Any,
    conversation_id: int,
    message_id: int,
) -> str:
    """Email managers when a client opens a new support thread.

    Only the chronologically first inbound message triggers mail. Later
    messages stay in the hub / push channels.
    """
    from supportchat.models import Conversation, Message, MessageDirection
    from supportchat.services import (
        render_support_first_inbound_notification,
        resolve_support_notify_recipients,
    )

    try:
        conversation = Conversation.objects.select_related(
            "assignee",
            "client",
            "lead",
        ).get(pk=conversation_id)
    except Conversation.DoesNotExist:
        logger.warning(
            "support_first_inbound_missing conversation_id=%s",
            conversation_id,
        )
        return "missing_conversation"

    try:
        message = Message.objects.get(pk=message_id, conversation_id=conversation_id)
    except Message.DoesNotExist:
        logger.warning(
            "support_first_inbound_missing message_id=%s conversation_id=%s",
            message_id,
            conversation_id,
        )
        return "missing_message"

    if message.direction != MessageDirection.INBOUND:
        return "skip_not_inbound"

    first = (
        Message.objects.filter(
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND,
        )
        .order_by("id")
        .first()
    )
    if first is None or first.pk != message.pk:
        return "skip_not_first"

    recipients = resolve_support_notify_recipients(conversation)
    if not recipients:
        logger.warning(
            "support_first_inbound_no_recipients conversation_id=%s",
            conversation_id,
        )
        return "no_recipients"

    subject, text_body, html_body = render_support_first_inbound_notification(
        conversation,
        message,
    )
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
    )
    email.attach_alternative(html_body, "text/html")
    try:
        email.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "support_first_inbound_send_failed conversation_id=%s",
            conversation_id,
        )
        raise self.retry(exc=exc)

    logger.info(
        "support_first_inbound_sent conversation_id=%s recipients=%s",
        conversation_id,
        len(recipients),
    )
    return "sent"


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
