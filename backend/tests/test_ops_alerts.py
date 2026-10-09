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


@patch("config.ops_alerts.publish_telegram")
def test_failed_ops_alert_releases_dedup_slot(publish_mock, settings) -> None:
    """Сбой Telegram раньше съедал ключ дедупа — тот же алерт молчал 15 минут."""
    from social.publishers import PublishResult

    settings.OPS_TELEGRAM_CHAT_IDS = ["12345"]
    publish_mock.return_value = PublishResult(ok=False, error="Telegram: URLError")
    assert send_ops_telegram_alert(title="HTTP 500", body="", dedup_key="http500:/x/") == 0

    publish_mock.return_value = PublishResult(ok=True)
    assert send_ops_telegram_alert(title="HTTP 500", body="", dedup_key="http500:/x/") == 1
    assert send_ops_telegram_alert(title="HTTP 500", body="", dedup_key="http500:/x/") == 0
    assert publish_mock.call_count == 2


def test_alert_without_chat_ids_keeps_dedup_slot_free(settings) -> None:
    """Пустой OPS_TELEGRAM_CHAT_IDS не должен занимать ключ на весь TTL."""
    settings.OPS_TELEGRAM_CHAT_IDS = []
    send_ops_telegram_alert(title="t", body="", dedup_key="no-chats")
    assert should_send_ops_alert("no-chats") is True


def test_stop_local_dev_lists_pids_without_matching_itself(tmp_path) -> None:
    """``ps aux | rg <pattern>`` находил собственный rg → kill мёртвого PID под set -e."""
    import subprocess
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "stop-local-dev.sh"
    text = script.read_text(encoding="utf-8")
    assert "ps aux" not in text
    assert 'pgrep -f "${pattern}" || true' in text
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "pgrep").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    (fake_bin / "pgrep").chmod(0o755)
    result = subprocess.run(
        ["bash", str(script)],
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "already stopped" in result.stdout


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


def test_middleware_queues_one_task_per_5xx_storm(settings, monkeypatch) -> None:
    """M39: шторм 5xx на одном пути ставит одну задачу, а не задачу на каждый запрос."""
    from django.core.cache import cache

    cache.clear()
    settings.DEBUG = False
    settings.OPS_TELEGRAM_CHAT_IDS = ["42"]
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(
        "accounts.tasks.send_ops_telegram_alert_task.delay",
        lambda **kwargs: calls.append(kwargs),
    )
    middleware = OpsTelegramAlertMiddleware(
        lambda _request: HttpResponse("err", status=500),
    )
    for _ in range(25):
        middleware(RequestFactory().get("/storm/"))
    middleware(RequestFactory().get("/other/"))
    assert [c["dedup_key"] for c in calls] == ["http500:/storm/", "http500:/other/"]


def test_middleware_returns_500_page_when_broker_down(settings, monkeypatch) -> None:
    """M39: недоступный Redis/брокер не превращает исходный 500 в падение middleware."""
    from django.core.cache import cache

    cache.clear()
    settings.DEBUG = False
    settings.OPS_TELEGRAM_CHAT_IDS = ["42"]

    def _broker_down(**_kwargs: str) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr("accounts.tasks.send_ops_telegram_alert_task.delay", _broker_down)
    middleware = OpsTelegramAlertMiddleware(
        lambda _request: HttpResponse("err", status=500),
    )
    response = middleware(RequestFactory().get("/catalog/"))
    assert response.status_code == 500
    assert response.content == b"err"


def test_middleware_survives_cache_outage(settings, monkeypatch) -> None:
    """M39: падение кэша при дедупе алерта не роняет ответ."""
    settings.DEBUG = False
    settings.OPS_TELEGRAM_CHAT_IDS = ["42"]

    def _cache_down(*_args: object, **_kwargs: object) -> bool:
        raise ConnectionError("redis down")

    monkeypatch.setattr("config.middleware.ops_telegram_alert.cache.add", _cache_down)
    middleware = OpsTelegramAlertMiddleware(
        lambda _request: HttpResponse("err", status=502),
    )
    assert middleware(RequestFactory().get("/x/")).status_code == 502


@patch("config.ops_alerts.publish_telegram")
def test_ops_telegram_alert_command(publish_mock, settings) -> None:
    from social.publishers import PublishResult

    settings.OPS_TELEGRAM_CHAT_IDS = ["99"]
    publish_mock.return_value = PublishResult(ok=True)
    call_command("ops_telegram_alert", message="health FAIL", dedup_key="monitor-test")
    publish_mock.assert_called_once()
