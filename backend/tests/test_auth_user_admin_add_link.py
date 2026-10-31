"""Regression: Unfold shows Add on auth User/Group changelists."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.urls import reverse

UserModel = get_user_model()


@pytest.mark.django_db
def test_user_changelist_shows_add_link_for_superuser(client) -> None:
    """Unfold add_link requires show_add_link; UserAdmin must expose Add."""
    admin = UserModel.objects.create_superuser(
        username="user-add-admin",
        email="user-add-admin@example.com",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_changelist"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "/admin/auth/user/add/" in html
    assert User in __import__("django.contrib.admin.sites", fromlist=["site"]).site._registry
    from django.contrib.admin.sites import site

    assert getattr(site._registry[User], "show_add_link", False) is True


@pytest.mark.django_db
def test_group_changelist_shows_add_link_for_superuser(client) -> None:
    """GroupAdmin also needs Unfold show_add_link for the Add button."""
    admin = UserModel.objects.create_superuser(
        username="group-add-admin",
        email="group-add-admin@example.com",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_group_changelist"))
    assert response.status_code == 200
    assert "/admin/auth/group/add/" in response.content.decode()


@pytest.mark.django_db
def test_user_changelist_shows_vk_column(client) -> None:
    """Staff VK profile must be visible on the user list like TG/MAX columns."""
    from accounts.models import StaffVkProfile

    admin = UserModel.objects.create_superuser(
        username="vk-col-admin",
        email="vk-col-admin@example.com",
        password="password12",
    )
    target = UserModel.objects.create_user(
        username="vk-col-manager",
        email="vk-col-manager@example.com",
        password="password12",
    )
    StaffVkProfile.objects.create(
        user=target,
        vk_user_id="424242",
        vk_alerts_enabled=True,
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_changelist"))
    assert response.status_code == 200
    html = response.content.decode()
    assert ">VK<" in html or "column-vk_user_short" in html
    assert "424242" in html


@pytest.mark.django_db
def test_vk_user_short_marks_disabled_alerts(client) -> None:
    """Muted VK alerts render as ``uid (выкл)`` like the TG/MAX siblings."""
    from django.contrib.admin.sites import site

    from accounts.models import StaffVkProfile

    admin_model = site._registry[User]
    user = UserModel(username="vk-off", email="vk-off@example.com")
    assert admin_model.vk_user_short(user) == "—"
    StaffVkProfile.objects.create(
        user=UserModel.objects.create_user(
            username="vk-off2",
            email="vk-off2@example.com",
            password="password12",
        ),
        vk_user_id="777",
        vk_alerts_enabled=False,
    )
    muted = UserModel.objects.get(username="vk-off2")
    assert admin_model.vk_user_short(muted) == "777 (выкл)"
