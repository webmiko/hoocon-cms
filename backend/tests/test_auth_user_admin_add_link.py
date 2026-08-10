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
