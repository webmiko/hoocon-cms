"""One empty inline row when a parent card has no lines yet."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from crm.models import Company, PlannedTouch

User = get_user_model()


@pytest.mark.django_db
def test_company_planned_calls_inline_shows_blank_row_when_empty(client) -> None:
    admin = User.objects.create_superuser(
        username="inline-blank-admin",
        email="inline-blank@example.com",
        password="password12",
    )
    company = Company.objects.create(name="Фирма без звонков")
    client.force_login(admin)
    html = client.get(reverse("admin:crm_company_change", args=[company.pk])).content.decode()
    assert 'name="planned_touches-0-title"' in html


@pytest.mark.django_db
def test_company_planned_calls_inline_hides_blank_row_when_touch_exists(client) -> None:
    admin = User.objects.create_superuser(
        username="inline-has-call",
        email="inline-has-call@example.com",
        password="password12",
    )
    company = Company.objects.create(name="Фирма со звонком")
    PlannedTouch.objects.create(company=company, title="Уже есть", starts_at=timezone.now())
    client.force_login(admin)
    html = client.get(reverse("admin:crm_company_change", args=[company.pk])).content.decode()
    assert 'name="planned_touches-0-title"' in html
    assert 'name="planned_touches-1-title"' not in html
