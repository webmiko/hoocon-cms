"""OpenAPI schema/docs are staff-only when DEBUG=False (audit P1-4)."""

from __future__ import annotations

import pytest
from django.test import Client, override_settings


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_anon_cannot_access_schema_when_not_debug() -> None:
    """Anonymous GET /api/schema/ redirects to login in prod-like settings."""
    response = Client().get("/api/schema/")
    assert response.status_code in {302, 403}
    if response.status_code == 302:
        assert "/admin/login" in response.url or "login" in response.url.lower()


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_anon_cannot_access_docs_when_not_debug() -> None:
    """Anonymous GET /api/docs/ redirects to login in prod-like settings."""
    response = Client().get("/api/docs/")
    assert response.status_code in {302, 403}
    if response.status_code == 302:
        assert "/admin/login" in response.url or "login" in response.url.lower()


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_staff_can_access_schema_when_not_debug(django_user_model) -> None:
    """Staff can open /api/schema/ when DEBUG=False."""
    user = django_user_model.objects.create_user(
        username="schema-staff",
        password="password12",
        is_staff=True,
    )
    client = Client()
    client.force_login(user)
    response = client.get("/api/schema/")
    assert response.status_code == 200
