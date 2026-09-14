"""Tests for staff MAX DM alerts."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.max_tasks import notify_staff_max_new_lead, notify_staff_max_support
from accounts.models import StaffMaxProfile
from accounts.roles import GROUP_MANAGER
from sitesettings.models import SiteSettings
from social.publishers import PublishResult


def _make_manager(*, email: str, user_id: str) -> object:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password="x",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffMaxProfile.objects.create(
        user=user,
        max_user_id=user_id,
        max_alerts_enabled=True,
    )
    return user


@pytest.mark.django_db
def test_lead_max_goes_to_manager() -> None:
    """New lead triggers MAX DM to manager with max_user_id."""
    _make_manager(email="mgr-max@hoocon.ru", user_id="111")
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Клиент",
        email="c@example.com",
        message="x" * 25,
        company="ООО",
    )
    with patch(
        "accounts.max_alerts.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_max_new_lead(lead.pk) == 1
    assert pub.call_args.kwargs["user_id"] == "111"


@pytest.mark.django_db
def test_lead_max_respects_site_flag() -> None:
    _make_manager(email="mgr-max2@hoocon.ru", user_id="111")
    site = SiteSettings.load()
    site.staff_max_leads_enabled = False
    site.save(update_fields=["staff_max_leads_enabled", "updated_at"])
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Клиент",
        email="c@example.com",
        message="x" * 25,
    )
    with patch("accounts.max_alerts.publish_max", return_value=PublishResult(ok=True)) as pub:
        assert notify_staff_max_new_lead(lead.pk) == 0
    pub.assert_not_called()


@pytest.mark.django_db
def test_support_max_alert() -> None:
    _make_manager(email="mgr-max3@hoocon.ru", user_id="222")
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    conv = Conversation.objects.create(
        channel=Channel.MAX,
        external_user_id="9000",
        display_name="Клиент",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен привод DA10N",
    )
    with patch(
        "accounts.max_alerts.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_max_support(conv.pk) == 1
    assert pub.call_args.kwargs["user_id"] == "222"
    alert = pub.call_args.kwargs["text"]
    assert "DA10N" in alert
    assert f"#{conv.pk}" in alert
    assert "Ответить из MAX" in alert
    assert "«Нужен привод DA10N»" in alert


@pytest.mark.django_db
def test_support_max_alert_uses_inbound_message_id() -> None:
    """Alert quotes the triggering inbound message, not a later one in the thread."""
    _make_manager(email="mgr-max4@hoocon.ru", user_id="333")
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    conv = Conversation.objects.create(
        channel=Channel.MAX,
        external_user_id="9001",
        display_name="Клиент",
    )
    first = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Старое сообщение",
    )
    second = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Новый вопрос по DA10",
    )
    with patch(
        "accounts.max_alerts.publish_max",
        return_value=PublishResult(ok=True),
    ) as pub:
        assert notify_staff_max_support(conv.pk, inbound_message_id=second.pk) == 1
    alert = pub.call_args.kwargs["text"]
    assert "Новый вопрос по DA10" in alert
    assert "Старое сообщение" not in alert
    assert first.pk != second.pk
