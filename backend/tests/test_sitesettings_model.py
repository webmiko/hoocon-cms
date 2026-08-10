"""Tests for sitesettings.SiteSettings singleton (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1 — SiteSettings.show_prices_on_site (default False,
security: цены скрыты по умолчанию; см. docs/security-baseline.md §3.2).
Паттерн singleton: одна строка с pk=1; load() — get_or_create.
"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_load_creates_singleton_if_missing() -> None:
    """SiteSettings.load() creates the single row on first call."""
    from sitesettings.models import SiteSettings

    settings = SiteSettings.load()
    assert settings.pk is not None
    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_load_returns_same_row_on_second_call() -> None:
    """Second load() returns the same row (singleton, not a new one)."""
    from sitesettings.models import SiteSettings

    first = SiteSettings.load()
    second = SiteSettings.load()
    assert first.pk == second.pk
    assert SiteSettings.objects.count() == 1


@pytest.mark.django_db
def test_default_show_prices_is_false() -> None:
    """Security default: show_prices_on_site is False (prices hidden)."""
    from sitesettings.models import SiteSettings

    settings = SiteSettings.load()
    assert settings.show_prices_on_site is False


@pytest.mark.django_db
def test_save_always_uses_pk_1_singleton() -> None:
    """Saving a new SiteSettings does not create a second row (pk forced to 1)."""
    from sitesettings.models import SiteSettings

    SiteSettings.load()
    new_one = SiteSettings(show_prices_on_site=True)
    new_one.save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().show_prices_on_site is True


@pytest.mark.django_db
def test_show_prices_can_be_toggled_true() -> None:
    """Flag can be enabled (admin toggles public price display)."""
    from sitesettings.models import SiteSettings

    settings = SiteSettings.load()
    settings.show_prices_on_site = True
    settings.save()
    assert SiteSettings.load().show_prices_on_site is True


@pytest.mark.django_db
def test_str_is_integrations_label() -> None:
    """__str__ is a short Russian Admin label for the singleton."""
    from sitesettings.models import SiteSettings

    settings = SiteSettings.load()
    assert str(settings) == "Интеграции сайта"
