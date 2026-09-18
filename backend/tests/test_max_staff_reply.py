"""Tests for staff support replies from personal MAX chat."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from accounts.models import StaffMaxProfile
from accounts.roles import GROUP_MANAGER
from social.max_bot import handle_max_update
from social.max_staff_reply import (
    parse_staff_reply_callback_payload,
    parse_staff_reply_text,
    staff_reply_callback_payload,
    staff_reply_hint,
    staff_support_alert_attachments,
)
from social.publishers import PublishResult
from supportchat.models import Channel, Conversation, Message, MessageDirection


def _make_manager(*, email: str, max_user_id: str) -> object:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password="x",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    ct = ContentType.objects.get_for_model(Conversation)
    perm = Permission.objects.get(
        content_type=ct,
        codename="change_conversation",
    )
    user.user_permissions.add(perm)
    StaffMaxProfile.objects.create(
        user=user,
        max_user_id=max_user_id,
        max_alerts_enabled=True,
    )
    return user


def test_parse_staff_reply_hash_and_command() -> None:
    """#ID and /reply ID both map to conversation id + body."""
    assert parse_staff_reply_text("#42 Здравствуйте!") == (42, "Здравствуйте!")
    assert parse_staff_reply_text("/reply 7 Да, есть на складе") == (7, "Да, есть на складе")


def test_staff_reply_hint_contains_id() -> None:
    assert "#15" in staff_reply_hint(15)
    assert "кнопка" in staff_reply_hint(15).casefold()


def test_staff_reply_callback_payload_roundtrip() -> None:
    payload = staff_reply_callback_payload(42)
    assert parse_staff_reply_callback_payload(payload) == 42
    assert parse_staff_reply_callback_payload("other") is None


def test_staff_support_alert_attachments_reply_button() -> None:
    attachments = staff_support_alert_attachments(7)
    keyboard = attachments[0]["payload"]["buttons"][0]
    callback_btn = next(btn for btn in keyboard if btn["type"] == "callback")
    assert callback_btn["text"] == "Ответить"
    assert parse_staff_reply_callback_payload(callback_btn["payload"]) == 7


@pytest.mark.django_db
def test_staff_plain_text_does_not_open_client_thread() -> None:
    """Manager free text must not be ingested as a client support thread."""
    _make_manager(email="mgr-reply@hoocon.ru", max_user_id="555")
    with patch(
        "social.max_bot.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 555, "first_name": "Mgr", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.mgr", "text": "привет"},
                },
            },
        )
    assert "не попадают в поддержку" in pub.call_args.kwargs["text"]
    assert not Conversation.objects.filter(channel=Channel.MAX, external_user_id="555").exists()


@pytest.mark.django_db
def test_staff_reply_button_then_text_delivers_to_client_max() -> None:
    """Callback «Ответить» sets dialog id; next plain text goes to the client."""
    from django.core.cache import cache

    cache.clear()
    _make_manager(email="mgr-cb@hoocon.ru", max_user_id="888")
    conv = Conversation.objects.create(
        channel=Channel.MAX,
        external_user_id="9000",
        display_name="Клиент",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен DA10",
    )
    callback_update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb.test",
            "payload": staff_reply_callback_payload(conv.pk),
            "user": {"user_id": 888, "first_name": "Mgr", "is_bot": False},
        },
    }
    with (
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as staff_pub,
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ) as ack,
    ):
        handle_max_update(callback_update)
    ack.assert_called_once()
    assert f"#{conv.pk}" in staff_pub.call_args.kwargs["text"]

    with (
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ),
        patch("supportchat.tasks.deliver_outbound_message.delay") as deliver,
    ):
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 888, "first_name": "Mgr", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.cb", "text": "Есть в наличии"},
                },
            },
        )
    deliver.assert_called_once()
    outbound = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
    ).get()
    assert outbound.body == "Есть в наличии"
    cache.clear()


@pytest.mark.django_db
def test_staff_hash_reply_delivers_to_client_max() -> None:
    """#ID text from manager reaches the client's MAX dialog."""
    _make_manager(email="mgr-reply2@hoocon.ru", max_user_id="777")
    conv = Conversation.objects.create(
        channel=Channel.MAX,
        external_user_id="9000",
        display_name="Клиент",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен DA10",
    )
    with (
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as staff_pub,
        patch("supportchat.tasks.deliver_outbound_message.delay") as deliver,
    ):
        handle_max_update(
            {
                "update_type": "message_created",
                "message": {
                    "sender": {"user_id": 777, "first_name": "Mgr", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.reply", "text": f"#{conv.pk} Есть в наличии"},
                },
            },
        )
    deliver.assert_called_once()
    outbound = Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
    ).get()
    assert outbound.body == "Есть в наличии"
    assert "Ответ отправлен" in staff_pub.call_args.kwargs["text"]
