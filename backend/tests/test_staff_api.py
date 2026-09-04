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
