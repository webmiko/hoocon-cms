"""Celery tasks for staff VK alerts."""

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
from supportchat.models import Channel, Conversation


@pytest.mark.django_db
def test_notify_staff_vk_new_lead_skips_when_disabled() -> None:
    site = SiteSettings.load()
    site.staff_vk_leads_enabled = False
    site.save()
    lead = Lead.objects.create(name="T", email="t@example.com")
    assert notify_staff_vk_new_lead(lead.pk) == 0


@pytest.mark.django_db
def test_notify_staff_vk_support_skips_when_disabled() -> None:
    site = SiteSettings.load()
    site.staff_vk_support_enabled = False
    site.save()
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="x")
    assert notify_staff_vk_support(conv.pk) == 0


@pytest.mark.django_db
def test_notify_staff_vk_support_sends_to_manager() -> None:
    site = SiteSettings.load()
    site.staff_vk_support_enabled = True
    site.save()
    user = get_user_model().objects.create_user(
        username="vk-task-mgr",
        email="vk-task-mgr@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(user=user, vk_user_id="700700", vk_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="web-vk-task")
    with patch("accounts.vk_alerts.send_vk_to_users", return_value=1) as send:
        sent = notify_staff_vk_support(conv.pk)
    assert sent == 1
    send.assert_called_once()


@pytest.mark.django_db
def test_notify_staff_vk_new_lead_missing_is_zero() -> None:
    site = SiteSettings.load()
    site.staff_vk_leads_enabled = True
    site.save()
    assert notify_staff_vk_new_lead(999_999) == 0


@pytest.mark.django_db
def test_notify_staff_vk_new_lead_sends_when_enabled() -> None:
    site = SiteSettings.load()
    site.staff_vk_leads_enabled = True
    site.save()
    lead = Lead.objects.create(name="VK lead", email="vk-lead@example.com")
    with patch("accounts.vk_alerts.send_vk_to_users", return_value=2):
        assert notify_staff_vk_new_lead(lead.pk) == 2


@pytest.mark.django_db
def test_notify_superuser_vk_crm_skips_when_disabled() -> None:
    site = SiteSettings.load()
    site.staff_vk_superuser_crm_enabled = False
    site.save()
    assert notify_superuser_vk_crm("CRM", "body", "/admin/") == 0


@pytest.mark.django_db
def test_notify_superuser_vk_crm_sends() -> None:
    site = SiteSettings.load()
    site.staff_vk_superuser_crm_enabled = True
    site.save()
    with patch("accounts.vk_alerts.send_vk_to_users", return_value=1):
        assert notify_superuser_vk_crm("CRM", "заметка", "/admin/") == 1


@pytest.mark.django_db
def test_retire_vk_support_alert_edits_author_message() -> None:
    site = SiteSettings.load()
    site.staff_vk_support_enabled = True
    site.save()
    user = get_user_model().objects.create_user(
        username="vk-retire",
        email="vk-retire@hoocon.ru",
        password="pw-12345",
        is_staff=True,
        first_name="Mgr",
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    StaffVkProfile.objects.create(user=user, vk_user_id="700701", vk_alerts_enabled=True)
    conv = Conversation.objects.create(channel=Channel.WEB, external_user_id="web-vk-retire")
    from social.publishers import PublishResult
    from social.vk_staff_reply import store_support_alert_mid

    store_support_alert_mid(conv.pk, "700701", "42", "alert")
    with patch(
        "social.publishers.edit_vk_message",
        return_value=PublishResult(ok=True),
    ) as edit:
        assert retire_vk_support_alert(conv.pk, user.pk) == 1
    assert edit.called
    kwargs = edit.call_args.kwargs
    assert "Вы ответили" in kwargs["message"]
