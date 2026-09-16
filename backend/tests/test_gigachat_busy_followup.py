"""Busy follow-up after escalation when staff do not open the chat."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from supportchat.gigachat.busy_followup import (
    build_busy_followup_message,
    escalation_needs_busy_followup,
)
from supportchat.models import Channel, Conversation, Message, MessageDirection
from supportchat.tasks import (
    _escalate_conversation,
    support_escalation_busy_followup,
)


@pytest.mark.django_db(transaction=True)
def test_escalation_schedules_busy_followup(django_capture_on_commit_callbacks) -> None:
    """После эскалации ставится отложенная задача на 5 минут."""
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="busy-sched")

    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.tasks.support_escalation_busy_followup.apply_async") as enqueue:
            _escalate_conversation(conv, reason="test", post_handoff=True)

    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["countdown"] == 300
    assert enqueue.call_args.kwargs["args"] == [conv.pk]


@pytest.mark.django_db
def test_busy_followup_sent_when_chat_still_unread(settings) -> None:
    """Если менеджер не открыл чат — бот просит email."""
    settings.SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS = 300
    now = timezone.now()
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-send",
        ai_active=False,
        ai_escalated_at=now,
        staff_unread_count=2,
        contact_email="",
    )

    result = support_escalation_busy_followup(conv.pk)

    assert result == "sent"
    msg = Message.objects.filter(conversation=conv, raw_payload__ai_busy_followup=True).first()
    assert msg is not None
    assert "email" in msg.body.lower()
    assert "занят" in msg.body.lower()


@pytest.mark.django_db
def test_busy_followup_skipped_when_staff_viewed() -> None:
    """Просмотренный чат (staff_unread=0) — без напоминания."""
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-read",
        ai_active=False,
        ai_escalated_at=timezone.now(),
        staff_unread_count=0,
    )

    assert escalation_needs_busy_followup(conv) is False
    assert support_escalation_busy_followup(conv.pk) == "skip"


@pytest.mark.django_db
def test_busy_followup_skipped_when_email_known() -> None:
    """Если email уже есть — не просим повторно."""
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-email",
        ai_active=False,
        ai_escalated_at=timezone.now(),
        staff_unread_count=1,
        contact_email="client@example.com",
    )

    assert escalation_needs_busy_followup(conv) is False


@pytest.mark.django_db
def test_busy_followup_skipped_after_staff_reply(django_user_model) -> None:
    """Ответ менеджера — без follow-up."""
    user = django_user_model.objects.create_user(
        username="mgr-busy",
        email="mgr@example.com",
        password="x",
        is_staff=True,
    )
    escalated_at = timezone.now()
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-reply",
        ai_active=False,
        ai_escalated_at=escalated_at,
        staff_unread_count=1,
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
        body="Здравствуйте!",
        author=user,
        created_at=escalated_at,
    )

    assert escalation_needs_busy_followup(conv) is False


def test_busy_followup_message_mentions_email() -> None:
    """Текст follow-up просит оставить email."""
    conv = Conversation(channel=Channel.WEB, external_user_id="x")
    text = build_busy_followup_message(conv)
    assert "email" in text.lower()
