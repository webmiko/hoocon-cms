"""Ops Telegram alerts: dedup, middleware 5xx hook, management command."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.http import HttpResponse
from django.test import RequestFactory

from config.middleware.ops_telegram_alert import OpsTelegramAlertMiddleware
from config.ops_alerts import send_ops_telegram_alert, should_send_ops_alert


@pytest.fixture(autouse=True)
def clear_ops_alert_cache() -> None:
    cache.clear()


@pytest.mark.django_db
def test_should_send_ops_alert_dedupes() -> None:
    assert should_send_ops_alert("http500:/catalog/") is True
    assert should_send_ops_alert("http500:/catalog/") is False


@patch("config.ops_alerts.publish_telegram")
def test_send_ops_telegram_alert_skips_without_chat_ids(
    publish_mock,
    settings,
) -> None:
    settings.OPS_TELEGRAM_CHAT_IDS = []
    sent = send_ops_telegram_alert(
        title="Test",
        body="body",
        dedup_key="unit-test",
    )
    assert sent == 0
    publish_mock.assert_not_called()


@patch("config.ops_alerts.publish_telegram")
def test_send_ops_telegram_alert_publishes(publish_mock, settings) -> None:
    from social.publishers import PublishResult

    settings.OPS_TELEGRAM_CHAT_IDS = ["12345"]
    publish_mock.return_value = PublishResult(ok=True)
    sent = send_ops_telegram_alert(
        title="HTTP 500",
        body="GET /catalog/",
        dedup_key="http500:/catalog/",
    )
    assert sent == 1
    publish_mock.assert_called_once()


def test_middleware_queues_task_on_500(settings, monkeypatch) -> None:
    settings.DEBUG = False
    settings.OPS_TELEGRAM_CHAT_IDS = ["42"]
    settings.SITE_URL = "https://hoocon.ru"
    calls: list[dict[str, str]] = []

    def _delay(**kwargs: str) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        "accounts.tasks.send_ops_telegram_alert_task.delay",
        _delay,
    )
    middleware = OpsTelegramAlertMiddleware(
        lambda _request: HttpResponse("err", status=500),
    )
    middleware(RequestFactory().get("/catalog/"))
    assert calls
    assert calls[0]["dedup_key"] == "http500:/catalog/"


def test_middleware_skips_health_and_debug(settings, monkeypatch) -> None:
    settings.DEBUG = True
    settings.OPS_TELEGRAM_CHAT_IDS = ["42"]
    called = False

    def _delay(**_kwargs: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "accounts.tasks.send_ops_telegram_alert_task.delay",
        _delay,
    )
    middleware = OpsTelegramAlertMiddleware(
        lambda _request: HttpResponse("err", status=500),
    )
    middleware(RequestFactory().get("/api/health/"))
    assert called is False


@patch("config.ops_alerts.publish_telegram")
def test_ops_telegram_alert_command(publish_mock, settings) -> None:
    from social.publishers import PublishResult

    settings.OPS_TELEGRAM_CHAT_IDS = ["99"]
    publish_mock.return_value = PublishResult(ok=True)
    call_command("ops_telegram_alert", message="health FAIL", dedup_key="monitor-test")
    publish_mock.assert_called_once()
