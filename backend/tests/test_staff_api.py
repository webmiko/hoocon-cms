"""Tests for staff mobile API."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, override_settings

from accounts.roles import GROUP_MANAGER
from leads.models import Lead
from staff_api.models import StaffAuthToken, StaffDevice

User = get_user_model()

STAFF_SETTINGS = {
    "STAFF_API_ENABLED": True,
    "ADMIN_EMAIL_OTP_ALLOWED_EMAILS": "",
    "ADMIN_EMAIL_OTP_REQUEST_LIMIT": 50,
    "AXES_ENABLED": False,
    "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
}


def _manager(*, email: str = "mgr@example.com") -> object:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="password12",
        is_staff=True,
        is_active=True,
    )
    group, _ = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    return user


def _auth_client(user: object) -> Client:
    token = StaffAuthToken.objects.create(user=user)
    client = Client()
    client.defaults["HTTP_AUTHORIZATION"] = f"Token {token.key}"
    return client


@pytest.mark.django_db
@override_settings(STAFF_API_ENABLED=False)
def test_staff_api_disabled_404() -> None:
    client = Client()
    response = client.post("/api/staff/auth/otp/start/", {"login": "a@b.c"}, content_type="application/json")
    assert response.status_code == 404


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_otp_start_verify_and_me() -> None:
    user = _manager()
    client = Client()
    with patch("staff_api.otp.generate_otp_code", return_value="123456"):
        with patch("config.admin_otp.send_admin_otp_email"):
            start = client.post(
                "/api/staff/auth/otp/start/",
                data={"login": user.email},
                content_type="application/json",
            )
    assert start.status_code == 200, start.content
    challenge_id = start.json()["challenge_id"]
    verify = client.post(
        "/api/staff/auth/otp/verify/",
        data={"challenge_id": challenge_id, "code": "123456"},
        content_type="application/json",
    )
    assert verify.status_code == 200, verify.content
    token = verify.json()["token"]
    assert StaffAuthToken.objects.filter(key=token, user=user).exists()

    me = Client().get("/api/staff/me/", HTTP_AUTHORIZATION=f"Token {token}")
    assert me.status_code == 200
    assert me.json()["email"] == user.email
    assert GROUP_MANAGER in me.json()["groups"]


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_badges_and_leads_scope() -> None:
    user = _manager()
    Lead.objects.create(
        lead_type=Lead.LeadType.CONSULTATION,
        name="Test",
        email="c@example.com",
        message="hi",
        status=Lead.LeadStatus.NEW,
    )
    client = _auth_client(user)
    badges = client.get("/api/staff/badges/")
    assert badges.status_code == 200
    assert "leads_new" in badges.json()
    assert "support_unread" in badges.json()

    leads = client.get("/api/staff/leads/")
    assert leads.status_code == 200
    assert leads.json()["count"] >= 1


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_lead_take() -> None:
    user = _manager(email="take@example.com")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="RFQ",
        email="rfq@example.com",
        company="Co",
        message="need quote",
        status=Lead.LeadStatus.NEW,
    )
    client = _auth_client(user)
    response = client.post(f"/api/staff/leads/{lead.pk}/take/")
    assert response.status_code == 200, response.content
    lead.refresh_from_db()
    assert lead.assignee_id == user.pk
    assert lead.status == Lead.LeadStatus.IN_PROGRESS


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_device_register_delete() -> None:
    user = _manager(email="push@example.com")
    client = _auth_client(user)
    created = client.post(
        "/api/staff/devices/",
        data={"fcm_token": "fcm-test-token-1", "platform": "android"},
        content_type="application/json",
    )
    assert created.status_code == 201, created.content
    pk = created.json()["id"]
    assert StaffDevice.objects.filter(pk=pk, user=user).exists()
    deleted = client.delete(f"/api/staff/devices/{pk}/")
    assert deleted.status_code == 204
    assert not StaffDevice.objects.filter(pk=pk).exists()


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_conversations_party_label_not_channel() -> None:
    """List/detail expose name·company or Пользователь·phone — never «Сайт» as title."""
    from crm.models import Client
    from supportchat.models import Channel, Conversation

    user = _manager(email="chatlabel@example.com")
    named = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-named-api",
        display_name="",
        status="open",
    )
    named.client = Client.objects.create(
        name="Пётр",
        email="petr@example.com",
        company="АО Ветер",
        phone="+79001234567",
    )
    named.save(update_fields=["client"])

    anon = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-anon-api",
        display_name="",
        contact_email="",
        status="open",
    )

    client = _auth_client(user)
    listing = client.get("/api/staff/conversations/")
    assert listing.status_code == 200
    by_id = {row["id"]: row for row in listing.json()["results"]}
    assert by_id[named.pk]["title"] == "Пётр · АО Ветер"
    assert by_id[named.pk]["display_name"] == "Пётр · АО Ветер"
    assert by_id[named.pk]["phone"] == "+79001234567"
    assert by_id[named.pk]["company"] == "АО Ветер"
    assert by_id[anon.pk]["title"] == "Пользователь"
    assert "Сайт" not in by_id[anon.pk]["title"]
    assert by_id[anon.pk]["channel_label"] == "Сайт"

    detail = client.get(f"/api/staff/conversations/{named.pk}/")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Пётр · АО Ветер"
    assert by_id[named.pk]["deletable"] is False
    assert by_id[anon.pk]["deletable"] is True


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_delete_unlinked_conversation_only() -> None:
    """DELETE removes anonymous chats; CRM-linked chats stay."""
    from crm.models import Client
    from supportchat.models import Channel, Conversation, Message, MessageDirection

    user = _manager(email="chatdel@example.com")
    linked = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-linked-del",
        status="open",
    )
    linked.client = Client.objects.create(
        name="CRM",
        email="crm-del@example.com",
        company="Co",
    )
    linked.save(update_fields=["client"])
    Message.objects.create(
        conversation=linked,
        direction=MessageDirection.INBOUND,
        body="keep me",
    )

    orphan = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-orphan-del",
        display_name="Спам",
        status="open",
        staff_unread_count=2,
    )
    Message.objects.create(
        conversation=orphan,
        direction=MessageDirection.INBOUND,
        body="delete me",
    )

    api = _auth_client(user)
    blocked = api.delete(f"/api/staff/conversations/{linked.pk}/")
    assert blocked.status_code == 400
    assert Conversation.objects.filter(pk=linked.pk).exists()

    ok = api.delete(f"/api/staff/conversations/{orphan.pk}/")
    assert ok.status_code == 204
    assert not Conversation.objects.filter(pk=orphan.pk).exists()
    assert not Message.objects.filter(conversation_id=orphan.pk).exists()


@pytest.mark.django_db
@override_settings(**STAFF_SETTINGS)
def test_logout_deletes_token() -> None:
    user = _manager(email="out@example.com")
    token = StaffAuthToken.objects.create(user=user)
    client = Client()
    response = client.post(
        "/api/staff/auth/logout/",
        HTTP_AUTHORIZATION=f"Token {token.key}",
    )
    assert response.status_code == 200
    assert not StaffAuthToken.objects.filter(key=token.key).exists()
