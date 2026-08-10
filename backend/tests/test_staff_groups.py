"""Staff Groups: Админ / Менеджер / Аналитик and their permissions."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from accounts.roles import (
    GROUP_ADMIN,
    GROUP_ANALYST,
    GROUP_MANAGER,
    STAFF_GROUP_PERMISSIONS,
)
from accounts.services import ensure_staff_groups

pytestmark = pytest.mark.django_db


def test_ensure_staff_groups_creates_three_named_groups() -> None:
    """Idempotent sync creates Админ, Менеджер, Аналитик."""
    ensure_staff_groups()
    names = set(Group.objects.values_list("name", flat=True))
    assert {GROUP_ADMIN, GROUP_MANAGER, GROUP_ANALYST} <= names

    ensure_staff_groups()
    assert Group.objects.filter(name=GROUP_ADMIN).count() == 1


def test_admin_group_has_full_catalog_and_sitesettings() -> None:
    """Админ can change catalog and site settings (secrets stay staff-only)."""
    ensure_staff_groups()
    group = Group.objects.get(name=GROUP_ADMIN)
    codenames = set(group.permissions.values_list("codename", flat=True))
    assert "change_sku" in codenames
    assert "delete_lead" in codenames
    assert "change_sitesettings" in codenames
    assert "add_redirect" in codenames


def test_manager_group_can_work_leads_without_delete_or_settings() -> None:
    """Менеджер: RFQ/CRM write, catalog view, no delete, no content/settings."""
    ensure_staff_groups()
    group = Group.objects.get(name=GROUP_MANAGER)
    codenames = set(group.permissions.values_list("codename", flat=True))
    assert "view_lead" in codenames
    assert "add_lead" in codenames
    assert "change_lead" in codenames
    assert "delete_lead" not in codenames
    assert "change_client" in codenames
    assert "add_emailmessage" in codenames
    assert "view_sku" in codenames
    assert "change_sku" not in codenames
    assert "view_page" not in codenames
    assert "view_socialpost" not in codenames
    assert "change_sitesettings" not in codenames
    assert "delete_sitesettings" not in codenames
    assert "view_user" in codenames


def test_analyst_group_is_read_only_same_surface_as_manager() -> None:
    """Аналитик: view leads/catalog/CRM (+ view_user), no write, no content."""
    ensure_staff_groups()
    group = Group.objects.get(name=GROUP_ANALYST)
    codenames = set(group.permissions.values_list("codename", flat=True))
    assert "view_lead" in codenames
    assert "view_sku" in codenames
    assert "view_client" in codenames
    assert "view_user" in codenames
    assert "add_lead" not in codenames
    assert "change_lead" not in codenames
    assert "delete_lead" not in codenames
    assert "change_client" not in codenames
    assert "view_page" not in codenames
    assert "view_redirect" not in codenames
    assert "view_socialpost" not in codenames
    assert "change_sitesettings" not in codenames


def test_ensure_staff_groups_replaces_drifted_permissions() -> None:
    """Sync restores exact matrix when an extra permission was added by hand."""
    ensure_staff_groups()
    group = Group.objects.get(name=GROUP_ANALYST)
    extra = Permission.objects.get(codename="change_lead", content_type__app_label="leads")
    group.permissions.add(extra)
    assert group.permissions.filter(codename="change_lead").exists()

    ensure_staff_groups()
    assert not group.permissions.filter(codename="change_lead").exists()


def test_sync_staff_groups_management_command() -> None:
    """``manage.py sync_staff_groups`` wires the same matrix."""
    call_command("sync_staff_groups")
    expected = STAFF_GROUP_PERMISSIONS[GROUP_MANAGER]
    group = Group.objects.get(name=GROUP_MANAGER)
    got = {(p.content_type.app_label, p.codename) for p in group.permissions.select_related("content_type")}
    assert got == expected
