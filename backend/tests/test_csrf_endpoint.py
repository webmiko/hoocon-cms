"""Tests for GET /api/csrf/ — CSRF token cookie endpoint.

Spec: ПЛАН §6 Iter 4 — F8 (Lead forms + CSRF).
"""

from __future__ import annotations

import pytest
from django.test import Client


@pytest.mark.django_db
def test_csrf_endpoint_returns_token_in_json() -> None:
    """GET /api/csrf/ returns 200 with a non-empty csrfToken field."""
    client = Client(enforce_csrf_checks=True)
    response = client.get("/api/csrf/")
    assert response.status_code == 200
    body = response.json()
    assert "csrfToken" in body
    assert isinstance(body["csrfToken"], str)
    assert len(body["csrfToken"]) > 0


@pytest.mark.django_db
def test_csrf_endpoint_sets_csrftoken_cookie() -> None:
    """GET /api/csrf/ sets the `csrftoken` cookie in the response."""
    client = Client(enforce_csrf_checks=True)
    response = client.get("/api/csrf/")
    assert response.status_code == 200
    # Cookie should be present in response.
    assert "csrftoken" in response.cookies


@pytest.mark.django_db
def test_csrf_endpoint_allows_anonymous() -> None:
    """GET /api/csrf/ works without authentication (AllowAny)."""
    client = Client()
    response = client.get("/api/csrf/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_csrf_endpoint_only_allows_get() -> None:
    """POST/PUT/DELETE to /api/csrf/ are not allowed (405)."""
    client = Client()
    for method in ("post", "put", "delete", "patch"):
        response = getattr(client, method)("/api/csrf/", {})
        assert response.status_code == 405, f"{method.upper()} should be 405"


@pytest.mark.django_db
def test_lead_post_with_csrf_token_succeeds() -> None:
    """POST /api/leads/ with a valid CSRF token from /api/csrf/ succeeds.

    This verifies the end-to-end CSRF flow: GET /api/csrf/ → cookie →
    POST /api/leads/ with X-CSRFToken header.
    """
    client = Client(enforce_csrf_checks=True)
    # Step 1: obtain CSRF token.
    csrf_response = client.get("/api/csrf/")
    token = csrf_response.json()["csrfToken"]
    # Step 2: POST a lead with the token in the X-CSRFToken header.
    payload = {
        "lead_type": "consultation",
        "name": "Иван Тестов",
        "email": "ivan.test@example.com",
        "message": "Тестовая заявка для проверки CSRF.",
    }
    response = client.post(
        "/api/leads/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 201, response.content
