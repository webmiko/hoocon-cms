"""Staff VK alert recipient helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import StaffVkProfile
from accounts.roles import GROUP_MANAGER
from accounts.vk_alerts import (
    format_staff_vk_message,
    send_vk_to_users,
    staff_vk_recipients_managers,
    vk_user_id_for,
)
from social.publishers import PublishResult


@pytest.mark.django_db
def test_vk_user_id_for_requires_enabled_profile() -> None:
    user = get_user_model().objects.create_user(
        username="vk-id",
        email="vk-id@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    StaffVkProfile.objects.create(user=user, vk_user_id="777", vk_alerts_enabled=False)
    assert vk_user_id_for(user) == ""
    user.vk_profile.vk_alerts_enabled = True
    user.vk_profile.save()
    assert vk_user_id_for(user) == "777"


@pytest.mark.django_db
def test_staff_vk_recipients_prefers_lead_assignee() -> None:
    mgr_a = get_user_model().objects.create_user(
        username="mgr-a",
        email="mgr-a@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    mgr_b = get_user_model().objects.create_user(
        username="mgr-b",
        email="mgr-b@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    for u in (mgr_a, mgr_b):
        u.groups.add(group)
        StaffVkProfile.objects.create(user=u, vk_user_id=f"id-{u.pk}", vk_alerts_enabled=True)
    qs = staff_vk_recipients_managers(lead_assignee_id=mgr_b.pk)
    assert list(qs.values_list("pk", flat=True)) == [mgr_b.pk]


def test_format_staff_vk_message_appends_admin_url(settings) -> None:
    settings.SITE_URL = "https://hoocon.ru"
    text = format_staff_vk_message(title="Заявка", body="Текст", url="/admin/leads/lead/1/")
    assert "Заявка" in text
    assert "https://hoocon.ru/admin/leads/lead/1/" in text


@pytest.mark.django_db
def test_send_vk_to_users_deduplicates_user_ids() -> None:
    user = get_user_model().objects.create_user(
        username="vk-send",
        email="vk-send@hoocon.ru",
        password="pw-12345",
        is_staff=True,
    )
    StaffVkProfile.objects.create(user=user, vk_user_id="888", vk_alerts_enabled=True)
    with patch(
        "accounts.vk_alerts.publish_vk_dm",
        return_value=PublishResult(ok=True, external_id="1"),
    ) as pub:
        sent = send_vk_to_users([user, user], "Привет")
    assert sent == 1
    assert pub.call_count == 1
