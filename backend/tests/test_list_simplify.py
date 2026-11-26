"""Lists for a manager hide what only the head of sales reads."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from leads.models import Lead
from supportchat.models import Conversation

User = get_user_model()


def _request(user: User) -> object:
    request = RequestFactory().get("/admin/")
    request.user = user
    return request


def _manager() -> User:
    ensure_staff_groups()
    user = User.objects.create_user(
        username="ls-mgr", email="ls-mgr@example.com", password="password12", is_staff=True
    )
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _boss() -> User:
    return User.objects.create_superuser(username="ls-boss", email="ls-boss@example.com", password="password12")


@pytest.mark.django_db
def test_lead_list_is_shorter_for_a_manager() -> None:
    model_admin = admin.site._registry[Lead]
    manager, boss = _request(_manager()), _request(_boss())

    manager_columns = model_admin.get_list_display(manager)
    boss_columns = model_admin.get_list_display(boss)
    manager_filters = [
        item if isinstance(item, str) else item[0]
        for item in model_admin.get_list_filter(manager)
        if isinstance(item, str | tuple)
    ]

    assert "rfq_thread_badge" in boss_columns and "processed_by" in boss_columns
    assert "rfq_thread_badge" not in manager_columns and "processed_by" not in manager_columns
    assert {"status", "lead_type", "created_at"} <= set(manager_filters)
    assert not {"processed_by", "assignee", "rfq_bundle_root", "seen_at", "work_labels"} & set(manager_filters)


@pytest.mark.django_db
def test_inbox_hides_rating_and_assignee_filter_from_a_manager_only() -> None:
    model_admin = admin.site._registry[Conversation]
    manager, boss = _request(_manager()), _request(_boss())

    assert "rating" not in model_admin.get_list_display(manager)
    assert "rating" in model_admin.get_list_display(boss)
    assert "assignee" not in model_admin.get_list_filter(manager)
    assert "assignee" in model_admin.get_list_filter(boss)
