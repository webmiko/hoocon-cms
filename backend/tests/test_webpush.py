"""Tests for Web Push subscribe API and delivery helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from webpush.models import PushSubscription
from webpush.services import send_push_to_subscription, upsert_subscription


def _csrf_client() -> Client:
    client = Client(enforce_csrf_checks=True)
    client.get("/api/csrf/")
    return client


@pytest.mark.django_db
def test_vapid_public_key_empty_when_unconfigured() -> None:
    client = Client()
    with override_settings(WEBPUSH_VAPID_PUBLIC_KEY="", WEBPUSH_VAPID_PRIVATE_KEY=""):
        resp = client.get("/api/webpush/vapid-public-key/")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtestpublickey",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private",
)
def test_subscribe_support_links_session() -> None:
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    resp = client.post(
        "/api/webpush/subscribe/",
        data={
            "endpoint": "https://push.example/sub/1",
            "keys": {"p256dh": "p256", "auth": "authkey"},
            "topic_support": True,
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 201
    sub = PushSubscription.objects.get(endpoint="https://push.example/sub/1")
    assert sub.topic_support is True
    assert sub.session_key  # support session uuid


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtestpublickey",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private",
)
def test_resubscribe_same_endpoint_keeps_row_and_topics() -> None:
    """Page reload re-POSTs the same endpoint — must not drop topics."""
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    payload = {
        "endpoint": "https://push.example/sub/persist",
        "keys": {"p256dh": "p256", "auth": "authkey"},
        "topic_support": True,
    }
    first = client.post(
        "/api/webpush/subscribe/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert first.status_code == 201
    sub = PushSubscription.objects.get(endpoint="https://push.example/sub/persist")
    session_a = sub.session_key
    assert sub.topic_support is True

    # Simulate reload: same browser endpoint, marketing added, support kept via OR.
    second = client.post(
        "/api/webpush/subscribe/",
        data={**payload, "topic_marketing": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
        HTTP_X_HOOCON_MARKETING_CONSENT="1",
    )
    assert second.status_code == 201
    assert PushSubscription.objects.filter(endpoint=payload["endpoint"]).count() == 1
    sub.refresh_from_db()
    assert sub.topic_support is True
    assert sub.topic_marketing is True
    assert sub.session_key == session_a


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtestpublickey",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private",
)
def test_subscribe_marketing_requires_consent_header() -> None:
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    payload = {
        "endpoint": "https://push.example/sub/mkt-gate",
        "keys": {"p256dh": "p256", "auth": "authkey"},
        "topic_marketing": True,
    }
    denied = client.post(
        "/api/webpush/subscribe/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert denied.status_code == 400
    assert PushSubscription.objects.count() == 0

    ok = client.post(
        "/api/webpush/subscribe/",
        data=payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
        HTTP_X_HOOCON_MARKETING_CONSENT="1",
    )
    assert ok.status_code == 201
    assert PushSubscription.objects.get().topic_marketing is True


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtestpublickey",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private",
)
def test_unsubscribe() -> None:
    upsert_subscription(
        endpoint="https://push.example/gone",
        p256dh="p",
        auth="a",
        topic_marketing=True,
    )
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    resp = client.post(
        "/api/webpush/unsubscribe/",
        data={"endpoint": "https://push.example/gone"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1
    assert PushSubscription.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtest",
    WEBPUSH_VAPID_PRIVATE_KEY="priv",
    WEBPUSH_VAPID_SUBJECT="mailto:test@hoocon.ru",
)
def test_send_deletes_on_410() -> None:
    sub = upsert_subscription(
        endpoint="https://push.example/dead",
        p256dh="p",
        auth="a",
        topic_support=True,
    )
    from pywebpush import WebPushException

    err = WebPushException("gone")
    err.response = MagicMock(status_code=410)
    with patch("pywebpush.webpush", side_effect=err):
        ok = send_push_to_subscription(sub, title="t", body="b")
    assert ok is False
    assert PushSubscription.objects.filter(pk=sub.pk).count() == 0


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_inbound_triggers_staff_push_task(django_capture_on_commit_callbacks) -> None:
    from supportchat.models import Channel, Conversation
    from supportchat.schedule import ensure_default_schedule
    from supportchat.services import add_inbound_message

    ensure_default_schedule()
    user = get_user_model().objects.create_user(
        username="staff@hoocon.ru",
        email="staff@hoocon.ru",
        password="x",
        is_staff=True,
    )
    upsert_subscription(
        endpoint="https://push.example/staff",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=user,
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-1",
        display_name="Client",
    )
    with patch("webpush.services.send_push_to_subscription", return_value=True) as send:
        with patch("supportchat.services.is_open_now", return_value=True):
            with django_capture_on_commit_callbacks(execute=True):
                add_inbound_message(conv, "hello")
    assert send.called


@pytest.mark.django_db
def test_admin_pushsubscription_changelist_shows_topics() -> None:
    staff = get_user_model().objects.create_superuser(
        username="admin",
        email="admin@hoocon.ru",
        password="x",
    )
    PushSubscription.objects.create(
        endpoint="https://push.example/admin-list",
        p256dh="p",
        auth="a",
        topic_support=True,
        topic_marketing=True,
        session_key="sess-admin-list",
    )
    client = Client()
    client.force_login(staff)
    resp = client.get("/admin/webpush/pushsubscription/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "hoocon-push-topic--support" in html
    assert "hoocon-push-topic--marketing" in html
    assert "hoocon-webpush.css" in html
    assert "Push-рассылка" in html


@pytest.mark.django_db
def test_admin_broadcast_form_renders_card() -> None:
    staff = get_user_model().objects.create_superuser(
        username="admin2",
        email="admin2@hoocon.ru",
        password="x",
    )
    PushSubscription.objects.create(
        endpoint="https://push.example/mkt",
        p256dh="p",
        auth="a",
        topic_marketing=True,
    )
    client = Client()
    client.force_login(staff)
    page = client.get("/admin/webpush/pushsubscription/broadcast/")
    assert page.status_code == 200
    html = page.content.decode()
    assert "hoocon-push-broadcast" in html
    assert 'name="title"' in html
    assert "Отправить рассылку" in html
    assert "получателей" in html


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtestpublickey",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private",
)
def test_clear_marketing_topic_keeps_support() -> None:
    client = _csrf_client()
    token = client.cookies["csrftoken"].value
    endpoint = "https://push.example/sub/topics"
    upsert_subscription(
        endpoint=endpoint,
        p256dh="p",
        auth="a",
        topic_support=True,
        topic_marketing=True,
    )
    resp = client.post(
        "/api/webpush/topics/",
        data={
            "endpoint": endpoint,
            "clear_marketing": True,
            "marketing_consent": False,
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is False
    assert body["topic_support"] is True
    assert body["topic_marketing"] is False
    assert body["marketing_consent"] is False
    sub = PushSubscription.objects.get(endpoint=endpoint)
    assert sub.topic_support is True
    assert sub.topic_marketing is False


def test_sanitize_push_url_blocks_protocol_relative() -> None:
    from webpush.services import sanitize_push_url

    assert sanitize_push_url("/?chat=1") == "/?chat=1"
    assert sanitize_push_url("//evil.example/phish") == "/"
    assert sanitize_push_url("https://evil.example/") == "/"
    assert sanitize_push_url("") == "/"
