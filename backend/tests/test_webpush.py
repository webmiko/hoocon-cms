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
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    FCM_SERVER_KEY="test-fcm-key",
    STAFF_API_ENABLED=True,
)
def test_inbound_bumps_support_sticker_and_triggers_push(
    django_capture_on_commit_callbacks,
) -> None:
    """Inbound bumps unread sticker (admin + staff badges) and fires Web Push + FCM."""
    from django.urls import reverse

    from staff_api.models import StaffAuthToken, StaffDevice
    from supportchat.models import Channel, Conversation
    from supportchat.schedule import ensure_default_schedule
    from supportchat.services import add_inbound_message, count_staff_unread

    ensure_default_schedule()
    user = get_user_model().objects.create_superuser(
        username="staff@hoocon.ru",
        email="staff@hoocon.ru",
        password="x",
    )
    upsert_subscription(
        endpoint="https://push.example/staff",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=user,
    )
    StaffDevice.objects.create(
        user=user,
        fcm_token="fcm-token-support-1",
        platform="android",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-1",
        display_name="Анна",
        staff_unread_count=0,
    )
    assert count_staff_unread() == 0

    admin = Client()
    admin.force_login(user)
    unread_url = reverse("admin:supportchat_conversation_unread_count")
    assert admin.get(unread_url).json()["count"] == 0

    token = StaffAuthToken.objects.create(user=user)
    staff_api = Client()
    badges0 = staff_api.get(
        "/api/staff/badges/",
        HTTP_AUTHORIZATION=f"Token {token.key}",
    )
    assert badges0.status_code == 200
    assert badges0.json()["support_unread"] == 0

    with patch("webpush.services.send_push_to_subscription", return_value=True) as web_send:
        with patch("staff_api.tasks._send_fcm", return_value=True) as fcm_send:
            with patch("supportchat.services.is_open_now", return_value=True):
                with django_capture_on_commit_callbacks(execute=True):
                    add_inbound_message(conv, "нужна помощь")

    conv.refresh_from_db()
    assert conv.staff_unread_count == 1
    assert count_staff_unread() == 1
    assert admin.get(unread_url).json()["count"] == 1
    badges1 = staff_api.get(
        "/api/staff/badges/",
        HTTP_AUTHORIZATION=f"Token {token.key}",
    )
    assert badges1.json()["support_unread"] == 1

    assert web_send.called
    web_kwargs = web_send.call_args.kwargs
    assert "поддержк" in web_kwargs["title"].casefold()
    assert web_kwargs["tag"] == f"support-{conv.pk}"
    assert f"/supportchat/conversation/{conv.pk}/" in web_kwargs["url"]

    assert fcm_send.called
    fcm_kwargs = fcm_send.call_args.kwargs
    assert fcm_kwargs["token"] == "fcm-token-support-1"
    assert "поддержк" in fcm_kwargs["title"].casefold()
    assert fcm_kwargs["data"]["type"] == "support"
    assert fcm_kwargs["data"]["conversation_id"] == str(conv.pk)

    change = admin.get(reverse("admin:supportchat_conversation_change", args=[conv.pk]))
    assert change.status_code == 200
    conv.refresh_from_db()
    assert conv.staff_unread_count == 0
    assert count_staff_unread() == 0
    assert admin.get(unread_url).json()["count"] == 0
    badges2 = staff_api.get(
        "/api/staff/badges/",
        HTTP_AUTHORIZATION=f"Token {token.key}",
    )
    assert badges2.json()["support_unread"] == 0


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


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_post_lead_triggers_staff_webpush(client, django_capture_on_commit_callbacks) -> None:
    """Public RFQ schedules Admin Web Push (same topic as support)."""
    from unittest.mock import patch

    user = get_user_model().objects.create_superuser(
        username="lead-push@hoocon.ru",
        email="lead-push@hoocon.ru",
        password="x",
    )
    upsert_subscription(
        endpoint="https://push.example/lead-staff",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=user,
    )
    payload = {
        "lead_type": "rfq",
        "name": "Пётр",
        "email": "petr@example.com",
        "company": "ООО Тест",
        "message": "Нужен подбор привода DA2MU для объекта.",
    }
    with patch("webpush.services.send_push_to_subscription", return_value=True) as web_send:
        with patch("staff_api.tasks._send_fcm", return_value=False):
            with django_capture_on_commit_callbacks(execute=True):
                resp = client.post(
                    "/api/leads/",
                    data=payload,
                    content_type="application/json",
                )
    assert resp.status_code == 201
    from leads.models import Lead

    lead = Lead.objects.get()
    assert web_send.called
    kwargs = web_send.call_args.kwargs
    assert kwargs["title"] == "Новая заявка"
    assert "Пётр" in kwargs["body"]
    assert kwargs["tag"] == f"lead-{lead.pk}"
    assert f"/admin/leads/lead/{lead.pk}/change/" in kwargs["url"]


@pytest.mark.django_db
def test_staff_subscribe_binds_user() -> None:
    """Authenticated staff subscribe stores user FK (required for staff alerts)."""
    staff = get_user_model().objects.create_user(
        username="mgr@hoocon.ru",
        email="mgr@hoocon.ru",
        password="x",
        is_staff=True,
    )
    client = Client()
    client.force_login(staff)
    endpoint = "https://push.example/staff-bind"
    resp = client.post(
        "/api/webpush/subscribe/",
        data={
            "endpoint": endpoint,
            "keys": {"p256dh": "pk", "auth": "ak"},
            "topic_support": True,
        },
        content_type="application/json",
    )
    assert resp.status_code in (200, 201)
    sub = PushSubscription.objects.get(endpoint=endpoint)
    assert sub.user_id == staff.pk
    assert sub.topic_support is True
    from webpush.services import queryset_staff_alerts

    assert queryset_staff_alerts().filter(pk=sub.pk).exists()


@pytest.mark.django_db
def test_admin_sw_js_served_with_scope_header() -> None:
    """Admin PWA SW is under /admin/ with Service-Worker-Allowed."""
    client = Client()
    resp = client.get("/admin/sw.js")
    assert resp.status_code == 200
    assert "javascript" in resp["Content-Type"]
    assert resp["Service-Worker-Allowed"] == "/admin/"
    assert b"showNotification" in resp.content
    assert "no-cache" in resp["Cache-Control"]


@pytest.mark.django_db
def test_staff_push_disabled_skips_lead_and_support() -> None:
    """SiteSettings flags gate staff Web Push tasks."""
    from sitesettings.models import SiteSettings
    from supportchat.models import Channel, Conversation
    from webpush.tasks import notify_staff_new_lead, notify_staff_support_inbound

    user = get_user_model().objects.create_superuser(
        username="gate@hoocon.ru",
        email="gate@hoocon.ru",
        password="x",
    )
    upsert_subscription(
        endpoint="https://push.example/gate",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=user,
    )
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Гейт",
        email="gate-lead@example.com",
        message="x" * 25,
        company="ООО Гейт",
    )
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-gate",
        display_name="Гость",
    )
    site = SiteSettings.load()
    site.staff_push_leads_enabled = False
    site.staff_push_support_enabled = False
    site.save(
        update_fields=[
            "staff_push_leads_enabled",
            "staff_push_support_enabled",
            "updated_at",
        ],
    )
    with patch("webpush.services.send_push_to_subscription", return_value=True) as send:
        assert notify_staff_new_lead(lead.pk) == 0
        assert notify_staff_support_inbound(conv.pk) == 0
    assert not send.called


@pytest.mark.django_db
def test_staff_push_uses_site_templates() -> None:
    """Custom title/body templates from SiteSettings are applied."""
    from sitesettings.models import SiteSettings
    from webpush.tasks import notify_staff_new_lead

    user = get_user_model().objects.create_superuser(
        username="tpl@hoocon.ru",
        email="tpl@hoocon.ru",
        password="x",
    )
    upsert_subscription(
        endpoint="https://push.example/tpl",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=user,
    )
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Анна",
        email="anna@example.com",
        message="x" * 25,
        company="ООО Анна",
        lead_type=Lead.LeadType.CONSULTATION,
    )
    site = SiteSettings.load()
    site.staff_push_lead_title = "RFQ alert"
    site.staff_push_lead_body = "Клиент {имя} — {тип}"
    site.save(
        update_fields=["staff_push_lead_title", "staff_push_lead_body", "updated_at"],
    )
    with patch("webpush.services.send_push_to_subscription", return_value=True) as send:
        assert notify_staff_new_lead(lead.pk) == 1
    kwargs = send.call_args.kwargs
    assert kwargs["title"] == "RFQ alert"
    assert kwargs["body"] == "Клиент Анна — Консультация"


@pytest.mark.django_db
def test_sitesettings_admin_shows_staff_push_fieldset() -> None:
    """Site settings change form exposes staff push controls and subscriber list."""
    staff = get_user_model().objects.create_superuser(
        username="push-set@hoocon.ru",
        email="push-set@hoocon.ru",
        password="x",
    )
    upsert_subscription(
        endpoint="https://push.example/listed",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=staff,
    )
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    client = Client()
    client.force_login(staff)
    resp = client.get(f"/admin/sitesettings/sitesettings/{site.pk}/change/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Уведомления на устройство" in html
    assert "staff_push_leads_enabled" in html
    assert "staff_push_lead_title" in html
    assert "push-set@hoocon.ru" in html
    assert "оповещения" in html


@pytest.mark.django_db
def test_admin_can_edit_staff_push_topic() -> None:
    """Staff can clear topic_support on a subscription from Admin."""
    admin_user = get_user_model().objects.create_superuser(
        username="edit-push@hoocon.ru",
        email="edit-push@hoocon.ru",
        password="x",
    )
    mgr = get_user_model().objects.create_user(
        username="mgr-push@hoocon.ru",
        email="mgr-push@hoocon.ru",
        password="x",
        is_staff=True,
    )
    sub = upsert_subscription(
        endpoint="https://push.example/edit-topic",
        p256dh="p",
        auth="a",
        topic_support=True,
        user=mgr,
    )
    client = Client()
    client.force_login(admin_user)
    resp = client.post(
        f"/admin/webpush/pushsubscription/{sub.pk}/change/",
        {
            "topic_support": "",
            "topic_marketing": "",
            "_save": "Save",
        },
    )
    assert resp.status_code in {200, 302}
    sub.refresh_from_db()
    assert sub.topic_support is False
