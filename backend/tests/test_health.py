"""Tests for /api/health/ endpoint (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1 — /api/health/ (version + db check) for smoke and
k8s-style probes. No auth; safe to expose (no secrets, no PII).
"""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_health_returns_200(client) -> None:
    """GET /api/health/ returns 200."""
    response = client.get("/api/health/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_health_payload_has_status_ok(client) -> None:
    """Payload contains status=ok."""
    response = client.get("/api/health/")
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_health_payload_has_version(client) -> None:
    """Payload contains a version string (SemVer)."""
    response = client.get("/api/health/")
    body = response.json()
    assert "version" in body
    assert isinstance(body["version"], str)
    assert body["version"]  # non-empty


@pytest.mark.django_db
def test_health_payload_has_db_check(client) -> None:
    """Payload reports db connectivity (db: ok)."""
    response = client.get("/api/health/")
    assert response.json()["db"] == "ok"


@pytest.mark.django_db
def test_health_is_read_only_no_auth(client) -> None:
    """Health endpoint is reachable by anonymous clients (no auth)."""
    # Already implied by client being anon, but make POST -> 405 explicit.
    response = client.post("/api/health/")
    assert response.status_code == 405


@pytest.mark.django_db
def test_health_does_not_leak_secrets(client) -> None:
    """Health response body must not contain SECRET_KEY or DB password."""
    from django.conf import settings

    response = client.get("/api/health/")
    body = response.content.decode()
    secret = settings.SECRET_KEY
    if secret and secret != "insecure-default-for-dev-only":
        assert secret not in body
    # No DB password leak either.
    assert "DB_PASSWORD" not in body
    assert "hoocon_local_dev" not in body
