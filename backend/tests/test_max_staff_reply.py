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
from social.max_staff_reply import parse_staff_reply_text, staff_reply_hint
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
    assert "Ответ клиенту" in pub.call_args.kwargs["text"]
    assert not Conversation.objects.filter(channel=Channel.MAX, external_user_id="555").exists()


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
