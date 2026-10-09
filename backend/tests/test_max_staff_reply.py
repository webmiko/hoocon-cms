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
    staff_user_for_max_user_id,
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


@pytest.mark.django_db
def test_staff_note_command_creates_internal_note() -> None:
    """#ID /note … stores a staff-only note, no client delivery."""
    from social.max_staff_reply import submit_staff_reply_from_max

    mgr = _make_manager(email="mgr-note@hoocon.ru", max_user_id="910")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-note",
    )
    with patch("supportchat.tasks.deliver_outbound_message.delay") as deliver:
        ok, status_text = submit_staff_reply_from_max(mgr, conv.pk, "/note позвонить завтра")
    assert ok
    assert "Заметка" in status_text
    note = Message.objects.get(conversation=conv, direction=MessageDirection.NOTE)
    assert note.body == "позвонить завтра"
    assert note.author_id == mgr.pk
    deliver.assert_not_called()


@pytest.mark.django_db
def test_staff_assign_command_reassigns_dialog() -> None:
    """#ID @handle transfers the dialog and logs an internal note."""
    from social.max_staff_reply import submit_staff_reply_from_max

    sender = _make_manager(email="mgr-x@hoocon.ru", max_user_id="911")
    target = _make_manager(email="valeriya@hoocon.ru", max_user_id="912")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-assign",
    )
    ok, status_text = submit_staff_reply_from_max(sender, conv.pk, "@valeriya@hoocon.ru")
    assert ok
    conv.refresh_from_db()
    assert conv.assignee_id == target.pk
    assert "передан" in status_text
    note = Message.objects.get(conversation=conv, direction=MessageDirection.NOTE)
    assert "передан" in note.body

    ok, status_text = submit_staff_reply_from_max(sender, conv.pk, "@ghost")
    assert not ok
    assert "не найден" in status_text


@pytest.mark.django_db(transaction=True)
def test_staff_assign_command_reassigns_dialog_autocommit() -> None:
    """Prod runs autocommit: /note and @handle must not crash on select_for_update.

    Plain ``django_db`` wraps tests in a transaction, hiding the missing
    ``transaction.atomic`` around the locked read — this one uses real commits.
    """
    from social.max_staff_reply import submit_staff_reply_from_max

    sender = _make_manager(email="mgr-autocommit@hoocon.ru", max_user_id="913")
    target = _make_manager(email="target-ac@hoocon.ru", max_user_id="914")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-assign-ac",
    )
    ok, status_text = submit_staff_reply_from_max(sender, conv.pk, "/note внутренняя проверка")
    assert ok, status_text
    assert Message.objects.filter(conversation=conv, direction=MessageDirection.NOTE).exists()

    ok, status_text = submit_staff_reply_from_max(sender, conv.pk, "@target-ac")
    assert ok, status_text
    conv.refresh_from_db()
    assert conv.assignee_id == target.pk


@pytest.mark.django_db
def test_staff_template_command_sends_canned_reply() -> None:
    """#ID /t slug expands the canned reply and delivers it to the client."""
    from social.max_staff_reply import submit_staff_reply_from_max
    from supportchat.models import ReplyTemplate

    mgr = _make_manager(email="mgr-tpl@hoocon.ru", max_user_id="913")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-tpl",
    )
    ReplyTemplate.objects.create(
        slug="dostavka",
        title="Сроки доставки",
        body="Отгрузка со склада 1–2 рабочих дня.",
    )
    with patch("supportchat.tasks.deliver_outbound_message.delay") as deliver:
        ok, status_text = submit_staff_reply_from_max(mgr, conv.pk, "/t dostavka")
    assert ok
    assert "Ответ отправлен" in status_text
    outbound = Message.objects.get(conversation=conv, direction=MessageDirection.OUTBOUND)
    assert outbound.body == "Отгрузка со склада 1–2 рабочих дня."
    deliver.assert_called_once()

    ok, status_text = submit_staff_reply_from_max(mgr, conv.pk, "/t")
    assert ok
    assert "/t dostavka" in status_text

    ok, status_text = submit_staff_reply_from_max(mgr, conv.pk, "/t missing")
    assert not ok
    assert "не найден" in status_text


@pytest.mark.django_db
def test_max_rating_callback_saves_score_for_dialog_owner() -> None:
    """⭐ tap on a rating request stores the score only for the dialog owner."""
    from supportchat.rating import support_rating_callback_payload

    conv = Conversation.objects.create(
        channel=Channel.MAX,
        external_user_id="42",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
        body="Ответ",
    )
    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb.rate",
            "payload": support_rating_callback_payload(conv.pk, 5),
            "user": {"user_id": 42, "first_name": "Client", "is_bot": False},
        },
    }
    with patch(
        "social.publishers.answer_max_callback",
        return_value=PublishResult(ok=True),
    ) as answer:
        handle_max_update(update)
    conv.refresh_from_db()
    assert conv.rating == 5
    assert "Спасибо" in answer.call_args.kwargs["notification"]

    # Stranger's press on the same payload must not rate the dialog.
    conv.rating = None
    conv.save(update_fields=["rating"])
    update["callback"]["user"]["user_id"] = 999
    update["callback"]["callback_id"] = "cb.rate2"
    with patch(
        "social.publishers.answer_max_callback",
        return_value=PublishResult(ok=True),
    ):
        handle_max_update(update)
    conv.refresh_from_db()
    assert conv.rating is None


@pytest.mark.django_db
def test_staff_lookup_prefers_account_with_reply_permission() -> None:
    """Duplicate max_user_id binding: pick the account that can actually reply.

    Regression: `.first()` could resolve a stale/test account without
    supportchat.change_conversation even when the real manager account has it.
    """
    conv_ct = ContentType.objects.get_for_model(Conversation)
    reply_perm = Permission.objects.get(
        content_type=conv_ct,
        codename="change_conversation",
    )
    group = Group.objects.get(name=GROUP_MANAGER)
    group.permissions.remove(reply_perm)

    stale = get_user_model().objects.create_user(
        username="mgr-stale@hoocon.ru",
        email="mgr-stale@hoocon.ru",
        password="x",
        is_staff=True,
        first_name="Stale",
    )
    stale.groups.add(group)
    StaffMaxProfile.objects.create(
        user=stale,
        max_user_id="900",
        max_alerts_enabled=True,
    )

    real = get_user_model().objects.create_user(
        username="mgr-real@hoocon.ru",
        email="mgr-real@hoocon.ru",
        password="x",
        is_staff=True,
        first_name="Real",
    )
    real.groups.add(group)
    real.user_permissions.add(reply_perm)
    StaffMaxProfile.objects.create(
        user=real,
        max_user_id="900",
        max_alerts_enabled=True,
    )

    assert staff_user_for_max_user_id("900") == real


@pytest.mark.django_db
def test_answered_alert_retires_reply_button_for_other_staff() -> None:
    """When one manager replies, others' alerts lose «Ответить» + get a mark."""
    from accounts.max_tasks import notify_staff_max_support, retire_max_support_alert
    from sitesettings.models import SiteSettings
    from social.max_staff_reply import load_support_alert_mid

    replier = _make_manager(email="mgr-a@hoocon.ru", max_user_id="501")
    other = _make_manager(email="mgr-b@hoocon.ru", max_user_id="502")

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-retire",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Сколько стоит DA10?",
    )
    site = SiteSettings.load()
    site.staff_max_support_enabled = True
    site.save(update_fields=["staff_max_support_enabled"])

    def _pub(*, user_id: str, text: str, attachments=None) -> PublishResult:
        return PublishResult(ok=True, external_id=f"mid-{user_id}")

    with patch("accounts.max_alerts.publish_max", side_effect=_pub):
        assert notify_staff_max_support(conv.pk) == 2

    assert load_support_alert_mid(conv.pk, "501")["mid"] == "mid-501"
    assert load_support_alert_mid(conv.pk, "502")["mid"] == "mid-502"

    with patch("social.publishers.edit_max_message") as edit:
        edited = retire_max_support_alert(conv.pk, replier.pk)
    assert edited == 2
    calls = {c.args[0]: c.kwargs["text"] for c in edit.call_args_list}
    replier_mid = load_support_alert_mid(conv.pk, replier.max_profile.max_user_id)["mid"]
    other_mid = load_support_alert_mid(conv.pk, other.max_profile.max_user_id)["mid"]
    assert replier_mid != other_mid
    assert "Вы ответили" in calls[replier_mid]
    assert "Ответил: Mgr" in calls[other_mid]
    for c in edit.call_args_list:
        assert c.kwargs["attachments"] == []


@pytest.mark.django_db
def test_reply_button_on_taken_dialog_is_rejected() -> None:
    """Second manager tapping «Ответить» on an assigned dialog gets a notice."""
    from social.max_staff_reply import staff_reply_callback_payload

    owner = _make_manager(email="mgr-owner@hoocon.ru", max_user_id="601")
    late = _make_manager(email="mgr-late@hoocon.ru", max_user_id="602")

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-taken",
        assignee=owner,
    )

    with (
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ) as answer,
        patch("social.max_bot._send_to_user") as send,
    ):
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "user": {"user_id": int(late.max_profile.max_user_id)},
                    "payload": staff_reply_callback_payload(conv.pk),
                    "callback_id": "cb-1",
                },
            },
        )
    answer.assert_called_once()
    assert "уже взял" in answer.call_args.kwargs["notification"]
    send.assert_not_called()


@pytest.mark.django_db
def test_max_photo_attachment_downloaded_into_inbox(settings, tmp_path) -> None:
    """MAX photo attachment url is downloaded and stored on the Message."""
    settings.MEDIA_ROOT = str(tmp_path)
    update = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 4321, "first_name": "Клиент", "is_bot": False},
            "recipient": {"chat_type": "dialog"},
            "body": {
                "mid": "mid.att1",
                "text": "",
                "attachments": [
                    {"type": "photo", "payload": {"url": "https://cdn.max.ru/x/pic.jpg"}},
                ],
            },
        },
    }
    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch(
            "social.publishers.max_download_attachment",
            return_value=(b"\xff\xd8\xff fake jpeg", "pic.jpg"),
        ) as dl,
    ):
        handle_max_update(update)
    dl.assert_called_once_with("https://cdn.max.ru/x/pic.jpg")
    conv = Conversation.objects.get(channel=Channel.MAX, external_user_id="4321")
    msg = Message.objects.get(conversation=conv)
    assert msg.attachment
    assert msg.attachment_name == "pic.jpg"
    assert msg.attachment_mime == "image/jpeg"
    assert msg.body.startswith("📎")

    # Idempotent by mid: second delivery of same update → no duplicate row.
    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch(
            "social.publishers.max_download_attachment",
            return_value=(b"\xff\xd8\xff fake jpeg", "pic.jpg"),
        ),
    ):
        handle_max_update(update)
    assert Message.objects.filter(conversation=conv).count() == 1


@pytest.mark.django_db
def test_max_attachment_download_failure_still_ingests_text() -> None:
    """If CDN download fails, the message text is still ingested (safe fallback)."""
    update = {
        "update_type": "message_created",
        "message": {
            "sender": {"user_id": 4322, "first_name": "Клиент", "is_bot": False},
            "recipient": {"chat_type": "dialog"},
            "body": {
                "mid": "mid.att2",
                "text": "вот файл",
                "attachments": [
                    {"type": "file", "payload": {"url": "https://cdn.max.ru/x/doc.pdf", "filename": "doc.pdf"}},
                ],
            },
        },
    }
    with (
        patch("supportchat.services.is_open_now", return_value=True),
        patch("social.publishers.max_download_attachment", return_value=None),
    ):
        handle_max_update(update)
    msg = Message.objects.get(
        conversation__channel=Channel.MAX,
        conversation__external_user_id="4322",
    )
    assert msg.body == "вот файл"
    assert not msg.attachment


@pytest.mark.django_db
def test_staff_alert_keyboard_has_note_and_assign_buttons() -> None:
    """Staff alert exposes «📝 Заметка» and «🔀 Передать» next to «Ответить»."""
    from social.max_staff_reply import (
        staff_assign_callback_payload,
        staff_note_callback_payload,
    )

    attachments = staff_support_alert_attachments(7)
    rows = attachments[0]["payload"]["buttons"]
    buttons = [btn for row in rows for btn in row]
    texts = [btn["text"] for btn in buttons if btn["type"] == "callback"]
    assert "Ответить" in texts
    assert "📝 Заметка" in texts
    assert "🔀 Передать" in texts
    payloads = {btn["text"]: btn["payload"] for btn in buttons if btn["type"] == "callback"}
    assert payloads["📝 Заметка"] == staff_note_callback_payload(7)
    assert payloads["🔀 Передать"] == staff_assign_callback_payload(7)
    # MAX API rejects wide rows — keep ≤2 buttons per row.
    assert all(len(row) <= 2 for row in rows)


@pytest.mark.django_db
def test_staff_note_button_then_text_stores_internal_note() -> None:
    """«📝 Заметка» puts the manager in note mode; next text is staff-only."""
    from django.core.cache import cache

    from social.max_staff_reply import staff_note_callback_payload

    cache.clear()
    _make_manager(email="mgr-note-btn@hoocon.ru", max_user_id="920")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-note-btn",
    )
    with (
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as staff_pub,
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ),
    ):
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "callback_id": "cb.note",
                    "payload": staff_note_callback_payload(conv.pk),
                    "user": {"user_id": 920, "first_name": "Mgr", "is_bot": False},
                },
            },
        )
    assert "заметкой" in staff_pub.call_args.kwargs["text"]

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
                    "sender": {"user_id": 920, "first_name": "Mgr", "is_bot": False},
                    "recipient": {"chat_type": "dialog"},
                    "body": {"mid": "mid.note-btn", "text": "перезвонить после обеда"},
                },
            },
        )
    deliver.assert_not_called()
    note = Message.objects.get(conversation=conv, direction=MessageDirection.NOTE)
    assert note.body == "перезвонить после обеда"
    assert not Message.objects.filter(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
    ).exists()
    cache.clear()


@pytest.mark.django_db
def test_staff_assign_button_shows_colleague_picker() -> None:
    """«🔀 Передать» sends a colleague picker keyboard to the manager."""
    from django.core.cache import cache

    from social.max_staff_reply import (
        parse_staff_alert_callback,
        staff_assign_callback_payload,
    )

    cache.clear()
    _make_manager(email="mgr-pick@hoocon.ru", max_user_id="930")
    colleague = _make_manager(email="colleague@hoocon.ru", max_user_id="931")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-pick",
    )
    with (
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as staff_pub,
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ),
    ):
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "callback_id": "cb.assign",
                    "payload": staff_assign_callback_payload(conv.pk),
                    "user": {"user_id": 930, "first_name": "Mgr", "is_bot": False},
                },
            },
        )
    call = staff_pub.call_args.kwargs
    assert f"#{conv.pk}" in call["text"]
    buttons = call["attachments"][0]["payload"]["buttons"]
    payloads = [row[0]["payload"] for row in buttons]
    parsed = [parse_staff_alert_callback(p) for p in payloads]
    assert ("assign_to", conv.pk, colleague.pk) in parsed
    assert all(p[2] != 930 for p in parsed if p)  # presser excluded
    cache.clear()


@pytest.mark.django_db
def test_staff_assign_to_button_reassigns_dialog() -> None:
    """Picking a colleague assigns the dialog and notifies the assignee."""
    from django.core.cache import cache

    from social.max_staff_reply import staff_assign_to_callback_payload

    cache.clear()
    _make_manager(email="mgr-send@hoocon.ru", max_user_id="940")
    target = _make_manager(email="mgr-get@hoocon.ru", max_user_id="941")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-assign-to",
    )
    with (
        patch(
            "social.publishers.publish_max",
            return_value=PublishResult(ok=True, external_id="mid-941"),
        ) as notify,
        patch(
            "social.max_bot.publish_max",
            return_value=PublishResult(ok=True),
        ) as staff_pub,
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ) as answer,
    ):
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "callback_id": "cb.assign-to",
                    "payload": staff_assign_to_callback_payload(conv.pk, target.pk),
                    "user": {"user_id": 940, "first_name": "Mgr", "is_bot": False},
                },
            },
        )
    conv.refresh_from_db()
    assert conv.assignee_id == target.pk
    assert "Передан" in answer.call_args.kwargs["notification"]
    assert "передан" in staff_pub.call_args.kwargs["text"]
    note = Message.objects.get(conversation=conv, direction=MessageDirection.NOTE)
    assert "передан" in note.body
    # Assignee ping went to their MAX with reply buttons.
    assert notify.call_args.kwargs["user_id"] == "941"
    assert notify.call_args.kwargs["attachments"]
    cache.clear()


@pytest.mark.django_db
def test_assign_to_button_requires_support_permission() -> None:
    """L18: кнопка «Передать» в MAX без supportchat.change_conversation не переназначает диалог."""
    from social.max_staff_reply import staff_assign_to_callback_payload

    presser = _make_manager(email="mgr-noperm@hoocon.ru", max_user_id="970")
    target = _make_manager(email="mgr-noperm-target@hoocon.ru", max_user_id="971")
    perm = Permission.objects.get(content_type__app_label="supportchat", codename="change_conversation")
    Group.objects.get(name=GROUP_MANAGER).permissions.remove(perm)
    presser.user_permissions.remove(perm)  # type: ignore[attr-defined]
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="web-noperm-assign")
    with patch(
        "social.publishers.answer_max_callback",
        return_value=PublishResult(ok=True),
    ) as answer:
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "user": {"user_id": 970},
                    "payload": staff_assign_to_callback_payload(conv.pk, target.pk),
                    "callback_id": "cb-noperm-assign",
                },
            },
        )
    conv.refresh_from_db()
    assert conv.assignee_id is None
    assert answer.call_args.kwargs["notification"] == "Недостаточно прав для ответа в поддержке."


@pytest.mark.django_db
def test_note_button_on_taken_dialog_is_rejected() -> None:
    """«📝 Заметка» on a dialog taken by someone else is refused."""
    from social.max_staff_reply import staff_note_callback_payload

    owner = _make_manager(email="mgr-own2@hoocon.ru", max_user_id="950")
    _make_manager(email="mgr-late2@hoocon.ru", max_user_id="951")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-taken-note",
        assignee=owner,
    )
    with (
        patch(
            "social.publishers.answer_max_callback",
            return_value=PublishResult(ok=True),
        ) as answer,
        patch("social.max_bot._send_to_user") as send,
    ):
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "user": {"user_id": 951},
                    "payload": staff_note_callback_payload(conv.pk),
                    "callback_id": "cb-taken-note",
                },
            },
        )
    assert "уже взял" in answer.call_args.kwargs["notification"]
    send.assert_not_called()


@pytest.mark.django_db
def test_assign_to_button_on_taken_dialog_is_rejected() -> None:
    """Stale transfer picker tap after the dialog was taken is refused."""
    from social.max_staff_reply import staff_assign_to_callback_payload

    owner = _make_manager(email="mgr-own3@hoocon.ru", max_user_id="960")
    _make_manager(email="mgr-late3@hoocon.ru", max_user_id="961")
    third = _make_manager(email="mgr-third@hoocon.ru", max_user_id="962")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-taken-assign",
        assignee=owner,
    )
    with patch(
        "social.publishers.answer_max_callback",
        return_value=PublishResult(ok=True),
    ) as answer:
        handle_max_update(
            {
                "update_type": "message_callback",
                "callback": {
                    "user": {"user_id": 961},
                    "payload": staff_assign_to_callback_payload(conv.pk, third.pk),
                    "callback_id": "cb-taken-assign",
                },
            },
        )
    assert "уже взял" in answer.call_args.kwargs["notification"]
    conv.refresh_from_db()
    assert conv.assignee_id == owner.pk
