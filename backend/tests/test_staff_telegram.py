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
