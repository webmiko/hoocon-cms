"""Tests for Django Admin registration (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1 — Admin для каталога + Redirect + SiteSettings;
docs/admin-vs-wagtail.md (редактор v1 = Django Admin).

Контракт: staff видит changelist; anon → login; SiteSettings — singleton
(нельзя add второй / delete).
"""

from __future__ import annotations

import pytest
from django.contrib.admin.sites import site
from django.urls import reverse

CATALOG_MODELS = (
    "catalog.Category",
    "catalog.Product",
    "catalog.SKU",
    "catalog.Attribute",
    "catalog.AttributeValue",
    "catalog.ProductFile",
)


def _model_by_label(label: str):
    """Import model class from 'app_label.ModelName'."""
    app_label, model_name = label.split(".")
    from django.apps import apps

    return apps.get_model(app_label, model_name)


@pytest.mark.parametrize("label", CATALOG_MODELS)
def test_catalog_model_registered_in_admin(label: str) -> None:
    """Each catalog model is registered with admin.site."""
    model = _model_by_label(label)
    assert model in site._registry


def test_redirect_registered_in_admin() -> None:
    """redirects.Redirect is registered."""
    from redirects.models import Redirect

    assert Redirect in site._registry


def test_sitesettings_registered_in_admin() -> None:
    """sitesettings.SiteSettings is registered."""
    from sitesettings.models import SiteSettings

    assert SiteSettings in site._registry


@pytest.mark.django_db
def test_anon_changelist_redirects_to_login(client) -> None:
    """Anonymous user cannot open SKU changelist (AuthN)."""
    url = reverse("admin:catalog_sku_changelist")
    response = client.get(url)
    assert response.status_code == 302
    assert "/admin/login" in response.url


@pytest.mark.django_db
def test_staff_changelist_ok_for_catalog_sku(client, django_user_model) -> None:
    """Staff (superuser) gets 200 on SKU changelist."""
    user = django_user_model.objects.create_user(
        username="editor",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    url = reverse("admin:catalog_sku_changelist")
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_staff_changelist_ok_for_redirect(client, django_user_model) -> None:
    """Staff (superuser) gets 200 on Redirect changelist."""
    user = django_user_model.objects.create_user(
        username="editor2",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    url = reverse("admin:redirects_redirect_changelist")
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_sitesettings_admin_disallows_add_when_exists(client, django_user_model) -> None:
    """SiteSettings Admin: no 'Add' when singleton already exists."""
    from sitesettings.models import SiteSettings

    SiteSettings.load()
    user = django_user_model.objects.create_user(
        username="editor3",
        password="test-pass-not-secret",
        is_staff=True,
        is_superuser=True,
    )
    client.force_login(user)
    url = reverse("admin:sitesettings_sitesettings_add")
    response = client.get(url)
    # Django returns 403 when has_add_permission is False.
    assert response.status_code == 403


@pytest.mark.django_db
def test_sitesettings_admin_disallows_delete() -> None:
    """SiteSettingsAdmin.has_delete_permission is always False."""
    from sitesettings.admin import SiteSettingsAdmin
    from sitesettings.models import SiteSettings

    SiteSettings.load()
    ma = SiteSettingsAdmin(SiteSettings, site)
    assert ma.has_delete_permission(request=None) is False  # type: ignore[arg-type]


@pytest.mark.django_db
def test_sku_admin_list_display_includes_sku_code() -> None:
    """SKUAdmin.list_display includes sku_code for operator UX."""
    from catalog.admin import SKUAdmin
    from catalog.models import SKU

    ma = SKUAdmin(SKU, site)
    assert "sku_code" in ma.list_display
    assert "slug" in ma.list_display


@pytest.mark.django_db
def test_product_file_admin_list_filter_includes_file_type() -> None:
    """ProductFileAdmin can filter by file_type (datasheet/certificate)."""
    from catalog.admin import ProductFileAdmin
    from catalog.models import ProductFile

    ma = ProductFileAdmin(ProductFile, site)
    assert "file_type" in ma.list_filter
