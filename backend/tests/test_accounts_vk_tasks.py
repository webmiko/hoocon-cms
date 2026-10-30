"""Staff VK alerts: flags, recipients, webpush fallback, retire text."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import StaffVkProfile
from accounts.roles import GROUP_MANAGER
from accounts.vk_tasks import (
    notify_staff_vk_new_lead,
    notify_staff_vk_support,
    notify_superuser_vk_crm,
    retire_vk_support_alert,
)
from leads.models import Lead
from sitesettings.models import SiteSettings
from social.publishers import PublishResult
from supportchat.models import Channel, Conversation, Message, MessageDirection


def _make_vk_manager(*, email: str, vk_user_id: str) -> object:
    user = get_user_model().objects.create_user(
        username=email,
        email=email,
        password="x",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(
        user=user,
        vk_user_id=vk_user_id,
        vk_alerts_enabled=True,
    )
    return user


def _make_vk_super(*, email: str, vk_user_id: str) -> object:
    user = get_user_model().objects.create_superuser(
        username=email,
        email=email,
        password="x",
        first_name="Admin",
    )
    StaffVkProfile.objects.create(
        user=user,
        vk_user_id=vk_user_id,
        vk_alerts_enabled=True,
    )
    return user


@pytest.mark.django_db
def test_lead_vk_goes_to_assignee_and_superuser() -> None:
    """Lead VK DM when recipients have no Web Push; flag off stops sending."""
    mgr = _make_vk_manager(email="mgr-vk@hoocon.ru", vk_user_id="111")
    _make_vk_super(email="su-vk@hoocon.ru", vk_user_id="222")
    lead = Lead.objects.create(
        name="Клиент",
        email="c@example.com",
        message="x" * 25,
        company="ООО",
        assignee=mgr,
    )
    with patch(
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="1"),
    ) as pub:
        assert notify_staff_vk_new_lead(lead.pk) == 2
    uids = {c.kwargs["user_id"] for c in pub.call_args_list}
    assert uids == {"111", "222"}
    text = pub.call_args_list[0].kwargs["text"]
    assert f"/admin/leads/lead/{lead.pk}/change/" in text

    site = SiteSettings.load()
    site.staff_vk_leads_enabled = False
    site.save(update_fields=["staff_vk_leads_enabled", "updated_at"])
    with patch("accounts.vk_alerts.publish_vk_dm") as pub2:
        assert notify_staff_vk_new_lead(lead.pk) == 0
    assert not pub2.called


@pytest.mark.django_db
def test_lead_vk_skipped_when_webpush_connected() -> None:
    """VK lead alerts are a fallback: skip users who already have staff Web Push."""
    mgr = _make_vk_manager(email="mgr-push-vk@hoocon.ru", vk_user_id="1010")
    su = _make_vk_super(email="su-push-vk@hoocon.ru", vk_user_id="2020")
    from webpush.services import upsert_subscription

    upsert_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/mgr-vk-connected",
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
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="1"),
    ) as pub:
        assert notify_staff_vk_new_lead(lead.pk) == 1
    assert pub.call_args.kwargs["user_id"] == "2020"

    upsert_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/su-vk-connected",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=su,
    )
    with patch("accounts.vk_alerts.publish_vk_dm") as pub2:
        assert notify_staff_vk_new_lead(lead.pk) == 0
    assert not pub2.called


@pytest.mark.django_db
def test_support_vk_alert_contains_client_text_and_keyboard() -> None:
    """VK support alert carries the inbound body and an «Ответить» button."""
    _make_vk_manager(email="mgr-vk-sup@hoocon.ru", vk_user_id="333")
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="s-vk",
        display_name="Олег",
    )
    inbound = Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Нужен привод на дымовой клапан 230В",
    )
    with patch(
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="42"),
    ) as pub:
        assert notify_staff_vk_support(conv.pk, inbound.pk) == 1
    kwargs = pub.call_args.kwargs
    assert kwargs["user_id"] == "333"
    assert "Нужен привод на дымовой клапан 230В" in kwargs["text"]
    assert f"#{conv.pk}" in kwargs["text"]
    assert "Олег" in kwargs["text"]
    assert "Ответить" in (kwargs.get("keyboard") or "")


@pytest.mark.django_db
def test_support_vk_parallel_despite_webpush() -> None:
    """Support VK is a parallel channel: webpush must not suppress it."""
    mgr = _make_vk_manager(email="mgr-vk-par@hoocon.ru", vk_user_id="9090")
    from webpush.services import upsert_subscription

    upsert_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/mgr-vk-support-parallel",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=mgr,
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="s-vk-par",
        display_name="Лев",
    )
    with patch(
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="1"),
    ) as pub:
        assert notify_staff_vk_support(conv.pk) == 1
    assert pub.call_args.kwargs["user_id"] == "9090"


@pytest.mark.django_db
def test_superuser_vk_crm_does_not_ping_managers() -> None:
    """CRM activity VK goes only to superusers, and only when the flag is on."""
    _make_vk_manager(email="mgr-crm-vk@hoocon.ru", vk_user_id="444")
    _make_vk_super(email="su-crm-vk@hoocon.ru", vk_user_id="555")
    site = SiteSettings.load()
    site.staff_vk_superuser_crm_enabled = False
    site.save(update_fields=["staff_vk_superuser_crm_enabled", "updated_at"])
    with patch("accounts.vk_alerts.publish_vk_dm") as pub:
        assert notify_superuser_vk_crm("CRM: активность", "заметка", "/admin/") == 0
    assert not pub.called

    site.staff_vk_superuser_crm_enabled = True
    site.save(update_fields=["staff_vk_superuser_crm_enabled", "updated_at"])
    with patch(
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="1"),
    ) as pub2:
        assert notify_superuser_vk_crm("CRM: активность", "заметка", "/admin/") == 1
    assert pub2.call_args.kwargs["user_id"] == "555"


@pytest.mark.django_db
def test_retire_vk_support_alert_author_vs_colleague_suffix() -> None:
    """Author sees «Вы ответили»; colleague sees who answered; keyboard cleared."""
    author = _make_vk_manager(email="vk-author@hoocon.ru", vk_user_id="7001")
    _make_vk_manager(email="vk-peer@hoocon.ru", vk_user_id="7002")
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="retire-vk")
    from social.vk_staff_reply import store_support_alert_mid

    store_support_alert_mid(conv.pk, "7001", "11", "alert")
    store_support_alert_mid(conv.pk, "7002", "22", "alert")
    with patch(
        "social.publishers.edit_vk_message",
        return_value=PublishResult(ok=True),
    ) as edit:
        assert retire_vk_support_alert(conv.pk, author.pk) == 2
    by_peer = {c.kwargs["peer_id"]: c.kwargs["message"] for c in edit.call_args_list}
    assert "Вы ответили" in by_peer["7001"]
    assert "Ответил: Mgr" in by_peer["7002"]
    for call in edit.call_args_list:
        assert '"buttons":[]' in call.kwargs["keyboard"]
