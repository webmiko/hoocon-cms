"""Tests for admin login throttle via django-axes (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1 — Throttle на admin login (решено: django-axes, не DRF);
docs/security-baseline.md §3.2 (rate limit login); БЗ Django-DRF-безопасность.md
(brute force: django-axes или DRF throttling).

django-axes blocks an IP after N failed login attempts within a time window.
We verify the configuration is active and the lockout triggers.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, override_settings


@pytest.fixture
def axes_client():
    """Client with a fixed REMOTE_ADDR so axes groups attempts by IP."""
    client = Client(REMOTE_ADDR="203.0.113.7")
    return client


@pytest.mark.django_db
def test_axes_is_installed() -> None:
    """django-axes is in INSTALLED_APPS."""
    assert "axes" in settings.INSTALLED_APPS


@pytest.mark.django_db
def test_axes_middleware_configured() -> None:
    """AxesMiddleware is in MIDDLEWARE."""
    assert any("axes" in m for m in settings.MIDDLEWARE)


@pytest.mark.django_db
def test_axes_backend_configured() -> None:
    """AxesStandaloneBackend is in AUTHENTICATION_BACKENDS."""
    assert any("axes" in b for b in settings.AUTHENTICATION_BACKENDS)


@pytest.mark.django_db
def test_axes_failure_limit_set() -> None:
    """AXES_FAILURE_LIMIT is a positive integer (lockout threshold)."""
    limit = getattr(settings, "AXES_FAILURE_LIMIT", None)
    assert isinstance(limit, int)
    assert limit > 0


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_axes_lockout_after_failure_limit(axes_client) -> None:
    """After AXES_FAILURE_LIMIT failed logins, the IP is locked out (403)."""
    limit = settings.AXES_FAILURE_LIMIT
    # Create a real staff user so the only reason login fails is the password.
    User.objects.create_user(
        username="editor",
        password="correct-pass-not-secret",
        is_staff=True,
    )

    # Send `limit` failed login attempts from the same IP.
    # The last attempt may itself trigger the lockout (429); that's expected.
    for i in range(limit):
        response = axes_client.post(
            "/admin/login/",
            {"username": "editor", "password": "wrong-pass", "next": "/admin/"},
        )
        # Failed login returns 200 (re-renders form) or 429 if axes locked
        # out on this very attempt (limit-th failure).
        assert response.status_code in (200, 302, 403, 429), f"iter {i}: {response.status_code}"

    # The next attempt from this IP must be blocked by axes.
    # django-axes 8.x returns 429 (Too Many Requests); older versions used 403.
    blocked = axes_client.post(
        "/admin/login/",
        {"username": "editor", "password": "correct-pass-not-secret", "next": "/admin/"},
    )
    assert blocked.status_code in (403, 429)


@pytest.mark.django_db
@override_settings(ADMIN_EMAIL_OTP_ENABLED=False)
def test_axes_does_not_block_correct_login_first_try(axes_client) -> None:
    """A correct login on the first attempt is not blocked."""
    User.objects.create_user(
        username="good",
        password="correct-pass-not-secret",
        is_staff=True,
    )
    response = axes_client.post(
        "/admin/login/",
        {"username": "good", "password": "correct-pass-not-secret", "next": "/admin/"},
    )
    # Successful admin login redirects (302) to /admin/.
    assert response.status_code == 302
    assert "/admin/" in response.url
