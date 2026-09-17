"""Busy follow-up after escalation when staff do not reply."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from supportchat.gigachat.busy_followup import (
    build_busy_followup_message,
    clear_staff_unread_allowed,
    escalation_needs_busy_followup,
    staff_acknowledgement_pending,
)
from supportchat.models import Channel, Conversation, Message, MessageDirection
from supportchat.services import add_inbound_message
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
def test_busy_followup_sent_when_manager_has_not_replied(settings) -> None:
    """Если менеджер не ответил — бот просит email."""
    settings.SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS = 300
    escalated_at = timezone.now() - timedelta(seconds=301)
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-send",
        ai_active=False,
        ai_escalated_at=escalated_at,
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
def test_busy_followup_not_skipped_when_staff_only_viewed_chat() -> None:
    """Просмотр чата без ответа менеджера — таймер и follow-up остаются."""
    escalated_at = timezone.now() - timedelta(seconds=301)
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-read",
        ai_active=False,
        ai_escalated_at=escalated_at,
        staff_unread_count=0,
    )

    assert staff_acknowledgement_pending(conv) is True
    assert clear_staff_unread_allowed(conv) is False
    assert escalation_needs_busy_followup(conv) is True
    assert support_escalation_busy_followup(conv.pk) == "sent"


@pytest.mark.django_db
def test_busy_followup_waits_until_delay_after_last_inbound(settings) -> None:
    """Таймер сбрасывается от последнего сообщения клиента."""
    settings.SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS = 300
    escalated_at = timezone.now() - timedelta(seconds=301)
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="busy-reset",
        ai_active=False,
        ai_escalated_at=escalated_at,
        staff_unread_count=1,
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="ещё одно сообщение",
        created_at=timezone.now() - timedelta(seconds=30),
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
        ai_escalated_at=timezone.now() - timedelta(seconds=301),
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
    escalated_at = timezone.now() - timedelta(seconds=301)
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

    assert staff_acknowledgement_pending(conv) is False
    assert escalation_needs_busy_followup(conv) is False


@pytest.mark.django_db(transaction=True)
def test_post_escalation_inbound_reschedules_busy_followup(
    settings,
    django_capture_on_commit_callbacks,
) -> None:
    """Новое сообщение клиента после handoff снова ставит таймер ожидания."""
    settings.SUPPORT_ESCALATION_BUSY_FOLLOWUP_SECONDS = 300
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="busy-inbound")
    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.tasks.support_escalation_busy_followup.apply_async") as enqueue:
            _escalate_conversation(conv, reason="test", post_handoff=True)
    assert enqueue.call_count == 1

    with django_capture_on_commit_callbacks(execute=True):
        with patch("supportchat.services.is_open_now", return_value=True):
            with patch("supportchat.tasks.support_escalation_busy_followup.apply_async") as enqueue2:
                add_inbound_message(conv, "уточнение по количеству")

    assert enqueue2.call_count == 1


def test_busy_followup_message_mentions_email() -> None:
    """Текст follow-up просит оставить email."""
    conv = Conversation(channel=Channel.WEB, external_user_id="x")
    text = build_busy_followup_message(conv)
    assert "email" in text.lower()


@pytest.mark.django_db
def test_admin_open_escalated_chat_does_not_clear_unread(django_user_model) -> None:
    """Эскалация: просмотр в админке не снимает непрочитанное до ответа менеджера."""
    from django.test import Client
    from django.urls import reverse

    staff = django_user_model.objects.create_superuser(
        username="esc-admin",
        email="esc-admin@example.com",
        password="x",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="esc-view",
        ai_active=False,
        ai_escalated_at=timezone.now(),
        staff_unread_count=2,
    )
    admin = Client()
    admin.force_login(staff)
    resp = admin.get(reverse("admin:supportchat_conversation_change", args=[conv.pk]))
    assert resp.status_code == 200
    conv.refresh_from_db()
    assert conv.staff_unread_count == 2


@pytest.mark.django_db
@override_settings(STAFF_API_ENABLED=True)
def test_staff_read_api_keeps_unread_until_manager_reply() -> None:
    """Staff /read/ не снимает badge, пока менеджер не написал в эскалированном чате."""
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group
    from django.test import Client

    from accounts.roles import GROUP_MANAGER
    from staff_api.tokens import issue_staff_token

    user = get_user_model().objects.create_user(
        username="esc-staff@example.com",
        email="esc-staff@example.com",
        password="x",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="esc-read",
        ai_active=False,
        ai_escalated_at=timezone.now(),
        staff_unread_count=3,
    )
    api = Client()
    api.defaults["HTTP_AUTHORIZATION"] = f"Token {issue_staff_token(user)}"
    resp = api.post(f"/api/staff/conversations/{conv.pk}/read/")
    assert resp.status_code == 200
    assert resp.json()["staff_unread_count"] == 3
    conv.refresh_from_db()
    assert conv.staff_unread_count == 3
