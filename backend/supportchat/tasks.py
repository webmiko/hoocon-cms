"""Celery tasks for support chat outbound delivery and staff email."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supportchat.models import Conversation

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
    if conversation.channel == Channel.MAX:
        if (msg.external_message_id or "").strip():
            return "already_delivered"
        from social.publishers import publish_max

        result = publish_max(
            user_id=conversation.external_user_id,
            text=msg.body,
        )
        if result.skipped:
            logger.warning("support_max_outbound_skipped message_id=%s", message_id)
            return "skipped"
        if not result.ok:
            logger.warning(
                "support_max_outbound_failed message_id=%s err=%s",
                message_id,
                (result.error or "")[:120],
            )
            raise self.retry(exc=RuntimeError(result.error or "max_failed"))
        if result.external_id and not msg.external_message_id:
            msg.external_message_id = result.external_id
            msg.save(update_fields=["external_message_id"])
        return "max_ok"
    logger.info(
        "support_outbound_channel_pending channel=%s message_id=%s",
        conversation.channel,
        message_id,
    )
    return "pending_channel"


_HANDOFF_TEXT = "Чат передан менеджеру — дальше ответит человек. Ожидайте, пожалуйста."
_MANAGER_ENGAGED_TEXT = "Менеджер уже ведёт этот диалог — напишите здесь, он увидит сообщение."


@shared_task(bind=True, max_retries=2, default_retry_delay=15)
def gigachat_reply(self: Any, conversation_id: int, inbound_message_id: int) -> str:
    """Generate GigaChat assistant reply for an inbound support message."""
    from django.db import transaction

    from supportchat.gigachat.busy_followup import manager_replied_after_escalation
    from supportchat.gigachat.chat_actions import inbound_continue_with_bot
    from supportchat.gigachat.client import GigachatError
    from supportchat.gigachat.delivery import deliver_ai_message
    from supportchat.gigachat.disclosure import apply_bot_disclosure
    from supportchat.gigachat.policy import (
        ai_assistant_enabled,
        ai_max_turns,
        conversation_ai_eligible,
    )
    from supportchat.gigachat.reply import generate_ai_reply
    from supportchat.models import Conversation, Message, MessageDirection, touch_conversation_message

    if not ai_assistant_enabled():
        return "disabled"

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return "missing_conversation"

    try:
        inbound = Message.objects.get(pk=inbound_message_id, conversation_id=conversation_id)
    except Message.DoesNotExist:
        return "missing_inbound"

    if inbound.direction != MessageDirection.INBOUND:
        return "skip_not_inbound"

    payload = inbound.raw_payload if isinstance(inbound.raw_payload, dict) else {}
    continue_bot = inbound_continue_with_bot(payload)

    if continue_bot:
        # «Продолжить с ботом»: возвращаем AI, если менеджер ещё не вступил.
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
            if conversation.ai_escalated_at is not None:
                if conversation.assignee_id is not None or manager_replied_after_escalation(conversation):
                    return _post_system_notice(conversation, _MANAGER_ENGAGED_TEXT)
                conversation.ai_active = True
                conversation.ai_escalated_at = None
            conversation.ai_turn_count = 0
            conversation.save(
                update_fields=["ai_active", "ai_escalated_at", "ai_turn_count", "updated_at"],
            )

    if not conversation_ai_eligible(conversation):
        if continue_bot:
            # Диалог уже у менеджера — объясняем, что кнопка не вернёт бота.
            return _post_system_notice(conversation, _MANAGER_ENGAGED_TEXT)
        return "not_eligible"

    from supportchat.gigachat.quiz_bot import QUIZ_ACTION_PREFIX, latest_quiz_message

    quiz_in_progress = latest_quiz_message(conversation) is not None or str(payload.get("chat_action", "")).startswith(
        QUIZ_ACTION_PREFIX
    )
    turn_cap = ai_max_turns() + (10 if quiz_in_progress else 0)
    if conversation.ai_turn_count >= turn_cap:
        from supportchat.gigachat.reply import turn_limit_reply

        ai = turn_limit_reply()
    else:
        try:
            ai = generate_ai_reply(conversation, inbound_message=inbound)
        except GigachatError as exc:
            logger.warning(
                "gigachat_reply_failed conversation_id=%s err=%s",
                conversation_id,
                str(exc)[:200],
            )
            raise self.retry(exc=exc)

    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        if not conversation_ai_eligible(conversation):
            return "not_eligible_race"
        first_turn = conversation.ai_turn_count == 0
        reply_body = apply_bot_disclosure(ai.text, first_turn=first_turn)
        raw_payload: dict[str, object] = {"ai": True}
        if ai.product_clarify:
            raw_payload["ai_product_clarify"] = True
        if ai.payload_extra:
            raw_payload.update(ai.payload_extra)
        if ai.escalate:
            raw_payload["ai_escalate"] = True
            if ai.escalation_note:
                raw_payload["manager_summary"] = ai.escalation_note[:500]
        msg = Message.objects.create(
            conversation=conversation,
            direction=MessageDirection.SYSTEM,
            body=reply_body,
            raw_payload=raw_payload,
        )
        conversation.ai_turn_count += 1
        conversation.save(update_fields=["ai_turn_count", "updated_at"])
        touch_conversation_message(conversation, inbound=False)

    deliver_ai_message(conversation, msg)

    if ai.escalate:
        return _escalate_conversation(
            conversation,
            reason="model_escalate",
            note=ai.escalation_note,
            post_handoff=False,
        )
    return "ok"


def _post_system_notice(conversation: Conversation, text: str) -> str:
    """Post and deliver a bot system line without touching AI state."""
    from supportchat.gigachat.delivery import deliver_ai_message
    from supportchat.models import Message, MessageDirection, touch_conversation_message

    msg = Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.SYSTEM,
        body=text,
        raw_payload={"ai": True, "ai_notice": True},
    )
    touch_conversation_message(conversation, inbound=False)
    deliver_ai_message(conversation, msg)
    return "notice"


def _escalate_conversation(
    conversation: Conversation,
    *,
    reason: str,
    note: str = "",
    post_handoff: bool = True,
) -> str:
    """Stop AI handling and optionally post handoff line to the visitor."""
    from django.db import transaction
    from django.db.models import F
    from django.utils import timezone

    from supportchat.gigachat.delivery import deliver_ai_message
    from supportchat.models import Conversation, Message, MessageDirection, touch_conversation_message
    from supportchat.services import _schedule_staff_support_push

    handoff = None
    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        if conversation.ai_escalated_at is not None:
            return f"already_escalated:{reason}"
        now = timezone.now()
        conversation.ai_active = False
        conversation.ai_escalated_at = now
        conversation.save(update_fields=["ai_active", "ai_escalated_at", "updated_at"])
        if post_handoff:
            handoff = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.SYSTEM,
                body=_HANDOFF_TEXT,
                raw_payload={"ai_handoff": True, "reason": reason, "note": note[:500]},
            )
            touch_conversation_message(conversation, inbound=False)
        Conversation.objects.filter(pk=conversation.pk).update(
            staff_unread_count=F("staff_unread_count") + 1,
            updated_at=now,
        )
        conversation.refresh_from_db(fields=["staff_unread_count", "updated_at"])

    if handoff is not None:
        deliver_ai_message(conversation, handoff)
    _schedule_staff_support_push(conversation.pk)
    _schedule_escalation_busy_followup(conversation.pk)
    logger.info(
        "gigachat_escalated conversation_id=%s reason=%s",
        conversation.pk,
        reason,
    )
    return f"escalated:{reason}"


def _schedule_escalation_busy_followup(conversation_id: int) -> None:
    """Enqueue busy follow-up if managers do not reply in time."""
    from django.db import transaction

    from supportchat.gigachat.busy_followup import escalation_busy_followup_seconds

    delay = escalation_busy_followup_seconds()

    def _enqueue() -> None:
        from supportchat.tasks import support_escalation_busy_followup

        support_escalation_busy_followup.apply_async(
            args=[conversation_id],
            countdown=delay,
        )

    transaction.on_commit(_enqueue)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def support_escalation_busy_followup(self: Any, conversation_id: int) -> str:
    """Ask for email when escalated chat has no manager reply within the delay."""
    from django.db import transaction

    from supportchat.gigachat.busy_followup import (
        build_busy_followup_message,
        escalation_needs_busy_followup,
    )
    from supportchat.gigachat.chat_actions import (
        actions_payload,
        continue_with_bot_actions,
    )
    from supportchat.gigachat.delivery import deliver_ai_message
    from supportchat.models import Conversation, Message, MessageDirection, touch_conversation_message

    try:
        conversation = Conversation.objects.get(pk=conversation_id)
    except Conversation.DoesNotExist:
        return "missing_conversation"

    if not escalation_needs_busy_followup(conversation):
        return "skip"

    with transaction.atomic():
        conversation = Conversation.objects.select_for_update().get(pk=conversation_id)
        if not escalation_needs_busy_followup(conversation):
            return "skip_race"
        msg = Message.objects.create(
            conversation=conversation,
            direction=MessageDirection.SYSTEM,
            body=build_busy_followup_message(conversation),
            raw_payload={
                "ai": True,
                "ai_busy_followup": True,
                **actions_payload(continue_with_bot_actions()),
            },
        )
        touch_conversation_message(conversation, inbound=False)

    deliver_ai_message(conversation, msg)
    logger.info(
        "support_busy_followup_sent conversation_id=%s",
        conversation_id,
    )
    return "sent"


_AUTO_CLOSED_TEXT = "Диалог закрыт по неактивности. Напишите здесь — продолжим с того же места."


def support_auto_close_hours() -> int:
    """Hours of silence after which an open conversation auto-closes."""
    raw = getattr(settings, "SUPPORT_AUTO_CLOSE_HOURS", 72)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 72


def support_empty_session_ttl_hours() -> int:
    """Hours after which a conversation without a single message is dropped."""
    raw = getattr(settings, "SUPPORT_EMPTY_SESSION_TTL_HOURS", 24)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 24


@shared_task(name="supportchat.housekeeping")
def supportchat_housekeeping() -> dict[str, int]:
    """Periodic sweep (django-celery-beat, every 15 min).

    1. Rescues busy follow-ups whose one-shot countdown task was lost.
    2. Auto-closes open conversations silent for SUPPORT_AUTO_CLOSE_HOURS
       (escalated ones still waiting for a manager stay open).
    3. Deletes CRM-unlinked sessions with zero messages older than the TTL.
    """
    from datetime import timedelta

    from django.db.models import Exists, OuterRef, Q
    from django.utils import timezone

    from supportchat.gigachat.busy_followup import escalation_needs_busy_followup
    from supportchat.models import (
        Conversation,
        ConversationStatus,
        Message,
        MessageDirection,
        touch_conversation_message,
    )

    now = timezone.now()
    stats = {"busy_followup": 0, "auto_closed": 0, "empty_deleted": 0}

    has_messages = Exists(Message.objects.filter(conversation=OuterRef("pk")))
    empty_cutoff = now - timedelta(hours=support_empty_session_ttl_hours())
    deleted, _ = (
        Conversation.objects.filter(
            created_at__lt=empty_cutoff,
            client__isnull=True,
            lead__isnull=True,
        )
        .exclude(has_messages)
        .delete()
    )
    stats["empty_deleted"] = deleted

    escalated = Conversation.objects.filter(
        status=ConversationStatus.OPEN,
        ai_escalated_at__isnull=False,
    )
    for conv in escalated.iterator():
        if escalation_needs_busy_followup(conv):
            support_escalation_busy_followup.delay(conv.pk)
            stats["busy_followup"] += 1

    manager_replied = Message.objects.filter(
        conversation=OuterRef("pk"),
        direction=MessageDirection.OUTBOUND,
        author__isnull=False,
        created_at__gte=OuterRef("ai_escalated_at"),
    )
    stale_cutoff = now - timedelta(hours=support_auto_close_hours())
    stale = Conversation.objects.filter(
        status=ConversationStatus.OPEN,
        last_message_at__lt=stale_cutoff,
    ).filter(
        # Безопасно закрывать: не эскалирован или менеджер уже ответил.
        # Эскалированные без ответа остаются — их видно фильтром «ждёт менеджера».
        Q(ai_escalated_at__isnull=True) | Exists(manager_replied),
    )
    for conv in stale.iterator():
        Message.objects.create(
            conversation=conv,
            direction=MessageDirection.SYSTEM,
            body=_AUTO_CLOSED_TEXT,
            raw_payload={"auto_closed": True},
        )
        conv.status = ConversationStatus.CLOSED
        conv.staff_unread_count = 0
        conv.save(update_fields=["status", "staff_unread_count", "updated_at"])
        touch_conversation_message(conv, inbound=False)
        stats["auto_closed"] += 1

    logger.info("supportchat_housekeeping %s", stats)
    return stats
