"""Tests for Russian Admin labels (apps, models, branding)."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

_EXPECTED_APP_NAMES = {
    "catalog": "Каталог",
    "content": "Контент",
    "leads": "Заявки",
    "crm": "CRM / клиенты",
    "redirects": "Редиректы",
    "sitesettings": "Настройки сайта",
    "social": "Соцсети / анонсы",
    "axes": "Защита входа",
    "django_celery_beat": "Периодические задачи",
}


@pytest.mark.parametrize(("label", "name"), sorted(_EXPECTED_APP_NAMES.items()))
def test_admin_app_verbose_name_is_russian(label: str, name: str) -> None:
    """Project and key third-party apps show Russian names in Admin index."""
    assert apps.get_app_config(label).verbose_name == name


@pytest.mark.django_db
def test_admin_index_has_no_english_app_headings() -> None:
    """Admin dashboard does not show English app group titles."""
    admin_user = User.objects.create_superuser(
        username="admin-ru",
        email="admin-ru@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    html = client.get("/admin/").content.decode()

    assert "Каталог" in html
    assert "Контент" in html
    assert "Заявки" in html
    assert "Редиректы" in html
    assert "Настройки сайта" in html
    assert "Защита входа" in html
    assert "Админка Hoocon" in html or "Панель управления" in html

    # App captions / module headings (avoid false positives like <!-- Content -->).
    for english in (
        ">Catalog<",
        ">Content<",
        ">Leads<",
        ">Redirects<",
        ">Sitesettings<",
        ">Axes<",
    ):
        assert english not in html


def test_sku_model_verbose_name_is_russian() -> None:
    """SKU model uses Russian verbose_name in Admin."""
    sku = apps.get_model("catalog", "SKU")
    assert "артикул" in str(sku._meta.verbose_name).lower()
    assert "SKU" in str(sku._meta.verbose_name)


def test_locale_middleware_is_enabled() -> None:
    """LocaleMiddleware activates Django's Russian admin translations."""
    from django.conf import settings

    assert "django.middleware.locale.LocaleMiddleware" in settings.MIDDLEWARE
