"""Public support widget API tests."""

from __future__ import annotations

from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from supportchat.models import Conversation
from supportchat.schedule import ensure_default_schedule

MSK = ZoneInfo("Europe/Moscow")


def _csrf_client() -> Client:
    client = Client(enforce_csrf_checks=True)
    client.get("/api/csrf/")
    return client


@pytest.mark.django_db
def test_schedule_endpoint_public() -> None:
    ensure_default_schedule()
    client = Client()
    resp = client.get("/api/support/schedule/")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_open_now" in data
    assert data["timezone"] == "Europe/Moscow"
    assert len(data["days"]) == 7


@pytest.mark.django_db
def test_channels_hides_tokens(settings) -> None:
    settings.TELEGRAM_BOT_USERNAME = "hoocon_bot"
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.telegram_enabled = True
    site.telegram_bot_token = "secret-token-value"
    site.save()
    client = Client()
    resp = client.get("/api/support/channels/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "secret-token-value" not in body
    assert resp.json()["channels"][0]["deep_link"] == "https://t.me/hoocon_bot"


@pytest.mark.django_db
def test_web_message_roundtrip_and_idor() -> None:
    ensure_default_schedule()
    with patch("supportchat.services.is_open_now", return_value=True):
        c1 = _csrf_client()
        token = c1.cookies["csrftoken"].value
        start = c1.post(
            "/api/support/conversations/",
            data={"display_name": "Ivan"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert start.status_code == 201
        assert start.json()["id"] is not None

        send = c1.post(
            "/api/support/conversations/current/messages/",
            data={"body": "Нужен КП"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert send.status_code == 201
        assert send.json()["message"]["body"] == "Нужен КП"

        listing = c1.get("/api/support/conversations/current/messages/")
        assert listing.status_code == 200
        assert len(listing.json()["messages"]) >= 1

    # Other session cannot see messages (empty own thread).
    c2 = Client()
    other = c2.get("/api/support/conversations/current/messages/")
    assert other.status_code == 200
    assert other.json()["messages"] == []


@pytest.mark.django_db
def test_outside_hours_auto_reply() -> None:
    ensure_default_schedule()
    with patch("supportchat.services.is_open_now", return_value=False):
        client = _csrf_client()
        token = client.cookies["csrftoken"].value
        client.post(
            "/api/support/conversations/",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        send = client.post(
            "/api/support/conversations/current/messages/",
            data={"body": "Поздно пишу"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        assert send.status_code == 201
        assert "auto_reply" in send.json()
        assert send.json()["message"]["outside_hours"] is True


@pytest.mark.django_db
def test_honeypot_silent_drop() -> None:
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    resp = client.post(
        "/api/support/conversations/",
        data={"website": "http://spam", "display_name": "Bot"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 201
    assert Conversation.objects.count() == 0
