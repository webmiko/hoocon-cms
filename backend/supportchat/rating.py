"""Client rating of a support dialog (one per conversation)."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from supportchat.models import Conversation, ConversationStatus, Message, MessageDirection
from supportchat.services import SupportChatError


def rate_conversation(conversation: Conversation, score: int) -> None:
    """Persist the one client rating 1–5; requires at least one assistant/staff reply."""
    if not isinstance(score, int) or not 1 <= score <= 5:
        raise SupportChatError("Оценка должна быть от 1 до 5.")
    has_reply = conversation.messages.filter(
        direction__in=(MessageDirection.OUTBOUND, MessageDirection.SYSTEM),
    ).exists()
    if not has_reply:
        raise SupportChatError("Пока нечего оценивать — дождитесь ответа.")
    now = timezone.now()
    updated = Conversation.objects.filter(pk=conversation.pk, rating__isnull=True).update(
        rating=score,
        rated_at=now,
        updated_at=now,
    )
    if not updated:
        raise SupportChatError("Оценка уже сохранена.")
    conversation.rating = score
    conversation.rated_at = now
    conversation.updated_at = now
    Message.objects.create(
        conversation=conversation,
        direction=MessageDirection.SYSTEM,
        body=f"Клиент оценил диалог: {score}/5",
        raw_payload={"rating": score},
    )


RATING_CALLBACK_PREFIX = "support_rate:"


def support_rating_callback_payload(conversation_id: int, score: int) -> str:
    """Inline-button payload ``support_rate:<conv>:<1..5>`` (TG/MAX)."""
    return f"{RATING_CALLBACK_PREFIX}{conversation_id}:{score}"


def parse_support_rating_callback(payload: str) -> tuple[int, int] | None:
    """Parse ``support_rate:<conv>:<score>`` → ``(conv_id, score)`` or None."""
    raw = (payload or "").strip()
    if not raw.startswith(RATING_CALLBACK_PREFIX):
        return None
    parts = raw[len(RATING_CALLBACK_PREFIX) :].split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    conv_id, score = int(parts[0]), int(parts[1])
    if not 1 <= score <= 5:
        return None
    return conv_id, score


def support_rating_reply_markup_tg(conversation_id: int) -> dict[str, Any]:
    """Telegram inline keyboard: ⭐1…⭐5 under the rating request."""
    buttons = [
        {
            "text": f"{n} ⭐",
            "callback_data": support_rating_callback_payload(conversation_id, n),
        }
        for n in range(1, 6)
    ]
    return {"inline_keyboard": [buttons]}


def support_rating_attachments_max(conversation_id: int) -> list[dict[str, Any]]:
    """MAX inline keyboard: ⭐1…⭐5 under the rating request."""
    buttons = [
        {
            "type": "callback",
            "text": f"{n} ⭐",
            "payload": support_rating_callback_payload(conversation_id, n),
        }
        for n in range(1, 6)
    ]
    return [{"type": "inline_keyboard", "payload": {"buttons": [buttons]}}]


def request_client_rating(conversation: Conversation) -> None:
    """Enqueue a rating request when a closed dialog has staff replies."""
    if conversation.status != ConversationStatus.CLOSED or conversation.rating is not None:
        return
    conversation_id = conversation.pk

    def _enqueue() -> None:
        from supportchat.tasks import send_rating_request

        send_rating_request.delay(conversation_id)

    transaction.on_commit(_enqueue)
