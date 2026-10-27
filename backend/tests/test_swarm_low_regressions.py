"""Regression tests for Security Swarm low/medium hardening (2026-10-27)."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from content.wiki_sanitize import sanitize_wiki_html
from webpush.models import PushSubscription
from webpush.services import upsert_subscription


def test_sanitize_wiki_html_strips_script_and_handlers() -> None:
    raw = (
        "<p>ok</p><script>alert(1)</script>"
        '<script src="/x.js" />'
        '<iframe src="https://evil.test"></iframe>'
        '<a href="javascript:evil()" onclick="hack()">x</a>'
    )
    cleaned = sanitize_wiki_html(raw)
    assert "<script" not in cleaned.casefold()
    assert "<iframe" not in cleaned.casefold()
    assert "javascript:" not in cleaned.casefold()
    assert "onclick" not in cleaned.casefold()
    assert "<p>ok</p>" in cleaned
    assert 'href="#"' in cleaned


def test_sanitize_wiki_html_empty_body_unchanged() -> None:
    assert sanitize_wiki_html("") == ""
    assert sanitize_wiki_html("   \n") == "   \n"


@pytest.mark.django_db
@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="BPtest",
    WEBPUSH_VAPID_PRIVATE_KEY="priv",
)
def test_subscribe_rejects_key_mismatch_on_existing_endpoint() -> None:
    upsert_subscription(
        endpoint="https://fcm.googleapis.com/fcm/send/existing",
        p256dh="owner-p",
        auth="owner-a",
        topic_support=True,
    )
    with pytest.raises(ValueError, match="keys mismatch"):
        upsert_subscription(
            endpoint="https://fcm.googleapis.com/fcm/send/existing",
            p256dh="attacker-p",
            auth="attacker-a",
            topic_support=True,
        )
    assert PushSubscription.objects.count() == 1


@pytest.mark.django_db
def test_rma_photo_rejects_oversized_upload() -> None:
    from accounts.models import ClientAccount
    from cabinet.serializers import RmaCaseCreateSerializer
    from catalog.validators import MAX_PRODUCT_IMAGE_SIZE_BYTES
    from crm.models import Client

    client = Client.objects.create(email="rma-size@corp.test", name="RMA")
    account = ClientAccount.objects.create(
        email=client.email,
        name="RMA",
        email_verified_at=timezone.now(),
    )
    client.account = account
    client.save(update_fields=["account"])
    payload = b"\xff\xd8\xff" + b"x" * (MAX_PRODUCT_IMAGE_SIZE_BYTES + 1)
    big = io.BytesIO(payload)
    big.name = "big.jpg"
    big.content_type = "image/jpeg"
    ser = RmaCaseCreateSerializer(
        data={"subject": "t", "description": "d", "photo": big},
        context={"client": client},
    )
    assert not ser.is_valid()
    assert "photo" in ser.errors


@pytest.mark.django_db
def test_rma_rejects_order_belonging_to_another_client() -> None:
    from accounts.models import ClientAccount
    from cabinet.models import Order, OrderStatus
    from cabinet.serializers import RmaCaseCreateSerializer
    from crm.models import Client

    owner = Client.objects.create(email="owner@corp.test", name="Owner")
    owner_account = ClientAccount.objects.create(
        email=owner.email,
        name="Owner",
        email_verified_at=timezone.now(),
    )
    owner.account = owner_account
    owner.save(update_fields=["account"])
    other = Client.objects.create(email="other@corp.test", name="Other")
    foreign_order = Order.objects.create(
        client=other,
        number="Z-foreign",
        status=OrderStatus.ACCEPTED,
    )

    ser = RmaCaseCreateSerializer(
        data={"subject": "t", "description": "d", "order": foreign_order.pk},
        context={"client": owner},
    )
    assert not ser.is_valid()
    assert "order" in ser.errors


@pytest.mark.django_db
def test_cabinet_password_login_uniform_fail_for_unknown_email() -> None:
    from cabinet.services import ClientAuthError, authenticate_password

    with pytest.raises(ClientAuthError, match="Неверная почта или пароль"):
        authenticate_password(email="nobody@example.com", password="password12")


@pytest.mark.django_db
def test_cabinet_otp_start_for_deactivated_account_is_decoy() -> None:
    from django.test import RequestFactory

    from accounts.models import ClientAccount
    from cabinet.services import start_client_otp

    ClientAccount.objects.create(email="deact@corp.test", name="X", is_active=False)
    payload = start_client_otp(RequestFactory().post("/"), "deact@corp.test", pdn_consent=True)
    assert payload["challenge_id"]
    assert "@" in payload["email_masked"]


@pytest.mark.django_db
def test_cabinet_decoy_otp_verify_never_issues_account() -> None:
    from django.test import RequestFactory

    from accounts.models import ClientAccount
    from cabinet.services import ClientAuthError, start_client_otp, verify_client_otp

    ClientAccount.objects.create(email="deact2@corp.test", name="X", is_active=False)
    with patch("cabinet.services.generate_otp_code", return_value="654321"):
        payload = start_client_otp(RequestFactory().post("/"), "deact2@corp.test", pdn_consent=True)
    with pytest.raises(ClientAuthError, match="Неверный код"):
        verify_client_otp(challenge_id=payload["challenge_id"], code="654321")


@pytest.mark.django_db
def test_admin_decoy_otp_correct_code_still_rejected() -> None:
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    from config.admin_otp import AdminOtpVerifyError, start_admin_otp_decoy, verify_admin_otp

    request = RequestFactory().post("/")
    request.session = SessionStore()
    with patch("config.admin_otp.generate_otp_code", return_value="111111"):
        start_admin_otp_decoy(request, login="unknown-admin", next_url="/admin/")
    with pytest.raises(AdminOtpVerifyError, match="Неверный код"):
        verify_admin_otp(request, "111111")
