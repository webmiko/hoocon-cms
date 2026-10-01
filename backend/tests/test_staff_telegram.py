"""Tests for staff Telegram DM alerts (managers vs superusers)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import StaffTelegramProfile
from accounts.roles import GROUP_MANAGER
from accounts.telegram_tasks import (
    notify_staff_telegram_new_lead,
    notify_staff_telegram_support,
    notify_superuser_telegram_crm,
)
from sitesettings.models import SiteSettings
from social.publishers import PublishResult
from social.telegram_bot import compose_chatid_reply, handle_telegram_update


def _make_manager(*, email: str, chat_id: str) -> object:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password="x",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffTelegramProfile.objects.create(
        user=user,
        telegram_chat_id=chat_id,
        telegram_alerts_enabled=True,
    )
    return user


def _make_super(*, email: str, chat_id: str) -> object:
    user = get_user_model().objects.create_superuser(
        username=email,
        email=email,
        password="x",
        first_name="Admin",
    )
    StaffTelegramProfile.objects.create(
        user=user,
        telegram_chat_id=chat_id,
        telegram_alerts_enabled=True,
    )
    return user


@pytest.mark.django_db
def test_chatid_command_returns_numeric_id() -> None:
    """/chatid replies with chat id and does not open support thread."""
    with patch(
        "social.telegram_bot.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_telegram_update(
            {
                "message": {
                    "message_id": 1,
                    "chat": {"id": 424242, "type": "private"},
                    "text": "/chatid",
                    "from": {"first_name": "Val"},
                },
            },
        )
    assert pub.called
    text = pub.call_args.kwargs["text"]
    assert "424242" in text
    assert "id чата" in text.casefold()


def test_compose_chatid_reply_escapes() -> None:
    assert "<code>99</code>" in compose_chatid_reply("99")


@pytest.mark.django_db
def test_lead_telegram_goes_to_manager_and_superuser() -> None:
    """New lead Telegram when recipients have no Web Push; respects SiteSettings."""
    mgr = _make_manager(email="mgr-tg@hoocon.ru", chat_id="111")
    _make_super(email="su-tg@hoocon.ru", chat_id="222")
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Клиент",
        email="c@example.com",
        message="x" * 25,
        company="ООО",
        assignee=mgr,
    )
    with patch(
        "accounts.telegram_alerts.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_telegram_new_lead(lead.pk) == 2
    chats = {c.kwargs["chat_id"] for c in pub.call_args_list}
    assert chats == {"111", "222"}

    site = SiteSettings.load()
    site.staff_telegram_leads_enabled = False
    site.save(update_fields=["staff_telegram_leads_enabled", "updated_at"])
    with patch("accounts.telegram_alerts.publish_telegram") as pub2:
        assert notify_staff_telegram_new_lead(lead.pk) == 0
    assert not pub2.called


@pytest.mark.django_db
def test_lead_telegram_skipped_when_webpush_connected() -> None:
    """Telegram is a fallback: skip users who already have staff Web Push."""
    mgr = _make_manager(email="mgr-push-tg@hoocon.ru", chat_id="1010")
    su = _make_super(email="su-push-tg@hoocon.ru", chat_id="2020")
    from leads.models import Lead
    from webpush.services import upsert_subscription

    upsert_subscription(
        endpoint="https://push.example/mgr-connected",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=mgr,
    )
    lead = Lead.objects.create(
        name="Клиент",
        email="c2@example.com",
        message="x" * 25,
        company="ООО",
        assignee=mgr,
    )
    with patch(
        "accounts.telegram_alerts.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_telegram_new_lead(lead.pk) == 1
    assert pub.call_args.kwargs["chat_id"] == "2020"

    upsert_subscription(
        endpoint="https://push.example/su-connected",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=su,
    )
    with patch("accounts.telegram_alerts.publish_telegram") as pub2:
        assert notify_staff_telegram_new_lead(lead.pk) == 0
    assert not pub2.called


@pytest.mark.django_db
def test_support_telegram_to_managers() -> None:
    _make_manager(email="mgr2-tg@hoocon.ru", chat_id="333")
    from supportchat.models import Channel, Conversation

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="s1",
        display_name="Анна",
    )
    with patch(
        "accounts.telegram_alerts.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_telegram_support(conv.pk) == 1
    assert pub.call_args.kwargs["chat_id"] == "333"


@pytest.mark.django_db
def test_crm_telegram_only_superuser_not_manager() -> None:
    """CRM stream skips managers; only superusers with chat id."""
    _make_manager(email="mgr3-tg@hoocon.ru", chat_id="444")
    _make_super(email="su2-tg@hoocon.ru", chat_id="555")
    with patch(
        "accounts.telegram_alerts.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_superuser_telegram_crm("CRM", "заметка", "/admin/") == 1
    assert pub.call_args.kwargs["chat_id"] == "555"
    assert "CRM" in pub.call_args.kwargs["text"]


@pytest.mark.django_db
def test_sitesettings_admin_shows_telegram_staff_fieldset(client) -> None:
    admin = get_user_model().objects.create_superuser(
        username="set-tg@hoocon.ru",
        email="set-tg@hoocon.ru",
        password="x",
    )
    StaffTelegramProfile.objects.create(
        user=admin,
        telegram_chat_id="777",
        telegram_alerts_enabled=True,
    )
    site = SiteSettings.load()
    client.force_login(admin)
    resp = client.get(f"/admin/sitesettings/sitesettings/{site.pk}/change/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Telegram персоналу" in html
    assert "staff_telegram_leads_enabled" in html
    assert "777" in html


@pytest.mark.django_db
def test_user_admin_shows_telegram_inline(client) -> None:
    admin = get_user_model().objects.create_superuser(
        username="ua-tg@hoocon.ru",
        email="ua-tg@hoocon.ru",
        password="x",
    )
    mgr = _make_manager(email="listed-tg@hoocon.ru", chat_id="888")
    client.force_login(admin)
    resp = client.get(f"/admin/auth/user/{mgr.pk}/change/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "telegram_chat_id" in html
    assert "888" in html


@pytest.mark.django_db
def test_staff_hash_reply_from_telegram_delivers_to_client() -> None:
    """#ID text from a manager's Telegram reaches the client's channel."""
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    _make_manager(email="mgr-reply-tg@hoocon.ru", chat_id="4141")
    conv = Conversation.objects.create(
        channel=Channel.TELEGRAM,
        external_user_id="client-9",
        display_name="Клиент",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен DA10",
    )
    with (
        patch(
            "social.telegram_bot.publish_telegram",
            return_value=PublishResult(ok=True),
        ) as pub,
        patch("supportchat.tasks.deliver_outbound_message.delay") as deliver,
    ):
        handle_telegram_update(
            {
                "message": {
                    "message_id": 10,
                    "chat": {"id": 4141, "type": "private"},
                    "text": f"#{conv.pk} Есть в наличии",
                    "from": {"id": 4141, "first_name": "Mgr"},
                },
            },
        )
    deliver.assert_called_once()
    outbound = Message.objects.get(conversation=conv, direction=MessageDirection.OUTBOUND)
    assert outbound.body == "Есть в наличии"
    assert "Ответ отправлен" in pub.call_args.kwargs["text"]


@pytest.mark.django_db
def test_staff_reply_button_then_text_from_telegram() -> None:
    """Callback «Ответить» sets pending dialog; next free text is the reply."""
    from django.core.cache import cache

    from social.telegram_staff_reply import staff_reply_callback_data
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    cache.clear()
    _make_manager(email="mgr-cb-tg@hoocon.ru", chat_id="5151")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-tg-cb",
    )
    with (
        patch("social.telegram_bot.telegram_api_call") as api,
        patch(
            "social.telegram_bot.publish_telegram",
            return_value=PublishResult(ok=True),
        ) as pub,
    ):
        handle_telegram_update(
            {
                "callback_query": {
                    "id": "cq-1",
                    "data": staff_reply_callback_data(conv.pk),
                    "from": {"id": 5151, "first_name": "Mgr"},
                },
            },
        )
    answer_call = api.call_args_list[0]
    assert answer_call.args[0] == "answerCallbackQuery"
    assert "Диалог #" in pub.call_args.kwargs["text"]

    with (
        patch(
            "social.telegram_bot.publish_telegram",
            return_value=PublishResult(ok=True),
        ),
        patch("supportchat.tasks.deliver_outbound_message.delay") as deliver,
    ):
        handle_telegram_update(
            {
                "message": {
                    "message_id": 11,
                    "chat": {"id": 5151, "type": "private"},
                    "text": "Ответ из Telegram",
                    "from": {"id": 5151, "first_name": "Mgr"},
                },
            },
        )
    deliver.assert_called_once()
    outbound = Message.objects.get(conversation=conv, direction=MessageDirection.OUTBOUND)
    assert outbound.body == "Ответ из Telegram"
    cache.clear()


@pytest.mark.django_db
def test_staff_free_text_in_telegram_does_not_open_client_thread() -> None:
    """Manager free text gets the staff notice, not a client conversation."""
    from supportchat.models import Channel, Conversation

    _make_manager(email="mgr-plain-tg@hoocon.ru", chat_id="6161")
    with patch(
        "social.telegram_bot.publish_telegram",
        return_value=PublishResult(ok=True),
    ) as pub:
        handle_telegram_update(
            {
                "message": {
                    "message_id": 12,
                    "chat": {"id": 6161, "type": "private"},
                    "text": "привет",
                    "from": {"id": 6161, "first_name": "Mgr"},
                },
            },
        )
    assert "не попадают в поддержку" in pub.call_args.kwargs["text"]
    assert not Conversation.objects.filter(
        channel=Channel.TELEGRAM,
        external_user_id="6161",
    ).exists()


@pytest.mark.django_db
def test_telegram_alert_button_retires_after_staff_reply() -> None:
    """Alert carries «Ответить»; after a reply all alerts lose the keyboard."""
    from accounts.telegram_tasks import retire_telegram_support_alert
    from social.telegram_staff_reply import load_support_alert_message_id
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    replier = _make_manager(email="mgr-a-tg@hoocon.ru", chat_id="7001")
    _make_manager(email="mgr-b-tg@hoocon.ru", chat_id="7002")

    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="web-tg-retire",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Сколько стоит DA10?",
    )
    site = SiteSettings.load()
    site.staff_telegram_support_enabled = True
    site.save(update_fields=["staff_telegram_support_enabled"])

    def _pub(*, chat_id: str, text: str, reply_markup=None, **kw) -> PublishResult:
        return PublishResult(ok=True, external_id=f"mid-{chat_id}")

    with patch("accounts.telegram_alerts.publish_telegram", side_effect=_pub) as pub:
        assert notify_staff_telegram_support(conv.pk) == 2
    markup = pub.call_args_list[0].kwargs["reply_markup"]
    assert markup["inline_keyboard"][0][0]["text"] == "Ответить"
    assert load_support_alert_message_id(conv.pk, "7001")["message_id"] == "mid-7001"

    with patch(
        "social.publishers.telegram_api_call",
        return_value=PublishResult(ok=True),
    ) as api:
        edited = retire_telegram_support_alert(conv.pk, replier.pk)
    calls = api.call_args_list
    texts = {c.args[1]["chat_id"]: c.args[1]["text"] for c in calls}
    assert edited == 2
    assert "Вы ответили" in texts["7001"]
    assert "Ответил: Mgr" in texts["7002"]


@pytest.mark.django_db
def test_activity_with_author_schedules_superuser_crm(
    django_capture_on_commit_callbacks,
) -> None:
    """Staff-authored Activity enqueues superuser Telegram CRM task."""
    su = _make_super(email="su3-tg@hoocon.ru", chat_id="999")
    from crm.models import Activity, ActivityType, Client

    client_row = Client.objects.create(name="C", email="act@example.com")
    with patch("accounts.tasks.notify_superuser_telegram_crm") as task:
        with django_capture_on_commit_callbacks(execute=True):
            Activity.objects.create(
                client=client_row,
                activity_type=ActivityType.NOTE,
                subject="Звонок клиенту",
                author=su,
            )
    assert task.delay.called
    args = task.delay.call_args.args
    assert "CRM" in args[0]
    assert "Звонок" in args[1]
