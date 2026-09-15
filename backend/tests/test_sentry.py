"""Sentry init is optional and gated on SENTRY_DSN."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.parametrize("dsn", ["", "   "])
def test_init_sentry_skips_without_dsn(monkeypatch: pytest.MonkeyPatch, dsn: str) -> None:
    """No SDK init when DSN is unset or blank."""
    monkeypatch.setenv("SENTRY_DSN", dsn)
    with patch("sentry_sdk.init") as init_mock:
        from config.sentry import init_sentry

        init_sentry()
    init_mock.assert_not_called()


def test_init_sentry_configures_django_and_celery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSN enables Django + Celery integrations with release label."""
    monkeypatch.setenv("SENTRY_DSN", "https://example@o0.ingest.sentry.io/1")
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
    with patch("sentry_sdk.init") as init_mock:
        from config.sentry import init_sentry

        init_sentry()
    init_mock.assert_called_once()
    kwargs = init_mock.call_args.kwargs
    assert kwargs["dsn"] == "https://example@o0.ingest.sentry.io/1"
    assert kwargs["environment"] == "staging"
    assert kwargs["release"].startswith("hoocon-cms@")
    assert kwargs["send_default_pii"] is False
    integration_names = {type(item).__name__ for item in kwargs["integrations"]}
    assert "DjangoIntegration" in integration_names
    assert "CeleryIntegration" in integration_names
