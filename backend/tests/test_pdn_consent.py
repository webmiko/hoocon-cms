"""M61: consent to PDN processing (152-ФЗ) is enforced and stored on the server.

Before: only the LeadForm checkbox existed (browser-side), nothing was saved,
and registration / code login / chat collected contacts with no consent at all.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import ClientAccount
from cabinet.services import ClientAuthError, _account_for_verified_email, _otp_key
from config.admin_otp import hash_otp_code
from config.pdn import PDN_CONSENT_REQUIRED
from leads.models import Lead
from supportchat.models import Conversation

_LEAD = {
    "lead_type": "rfq",
    "name": "Иван",
    "email": "ivan@example.com",
    "company": "ООО Ромашка",
    "message": "Нужен КП на приводы для объекта.",
}


@pytest.fixture(autouse=True)
def _cabinet_on(db: None) -> None:
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.cabinet_enabled = True
    site.save()


@pytest.mark.django_db
@pytest.mark.parametrize("consent", [None, False, "нет"])
def test_lead_without_consent_is_rejected(client, consent: object) -> None:
    payload = dict(_LEAD) if consent is None else {**_LEAD, "pdn_consent": consent}
    response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 400
    assert PDN_CONSENT_REQUIRED in str(response.json()["pdn_consent"])
    assert not Lead.objects.exists()


@pytest.mark.django_db
@override_settings(PDN_POLICY_VERSION="2026-10-09")
def test_lead_stores_consent_time_and_policy_version(client) -> None:
    response = client.post("/api/leads/", data={**_LEAD, "pdn_consent": True}, content_type="application/json")
    assert response.status_code == 201, response.content
    lead = Lead.objects.get()
    assert lead.pdn_consent_at is not None
    assert lead.pdn_policy_version == "2026-10-09"
    assert "pdn_consent" not in response.json()


def _post_auth(api: APIClient, path: str, **extra: object):
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        return api.post(
            path,
            {"email": "new@acme.test", "password": "sup3r-secret!", "form_start_ts": time.time() - 10, **extra},
            format="json",
        )


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/auth/register/", "/api/auth/otp/start/"])
def test_account_forms_require_consent(path: str) -> None:
    response = _post_auth(APIClient(), path)
    assert response.status_code == 400
    assert "pdn_consent" in response.json()


@pytest.mark.django_db
@override_settings(PDN_POLICY_VERSION="2026-10-09")
def test_verified_registration_stamps_consent_on_account() -> None:
    api = APIClient()
    challenge = _post_auth(api, "/api/auth/register/", pdn_consent=True).json()["challenge_id"]
    payload = cache.get(_otp_key(challenge))
    cache.set(_otp_key(challenge), {**payload, "code_hash": hash_otp_code("424242")}, timeout=300)
    verified = api.post("/api/auth/otp/verify/", {"challenge_id": challenge, "code": "424242"}, format="json")
    assert verified.status_code == 200, verified.content
    account = ClientAccount.objects.get(email="new@acme.test")
    assert account.pdn_consent_at is not None
    assert account.pdn_policy_version == "2026-10-09"


@pytest.mark.django_db
def test_no_account_is_created_from_a_challenge_without_consent() -> None:
    """Root invariant: even a valid code cannot create an account without consent."""
    with pytest.raises(ClientAuthError, match="согласие"):
        _account_for_verified_email({"email": "raw@acme.test", "pending": None, "pdn_consent": False})
    assert not ClientAccount.objects.filter(email="raw@acme.test").exists()


def _start_chat(api: APIClient, **data: object):
    api.get("/api/csrf/")
    return api.post("/api/support/conversations/", data, format="json")


@pytest.mark.django_db
def test_chat_contacts_need_consent_and_nothing_is_saved_without_it() -> None:
    api = APIClient()
    response = _start_chat(api, display_name="Анна", contact_email="anna@acme.test")
    assert response.status_code == 400
    assert response.json()["detail"] == PDN_CONSENT_REQUIRED
    assert not Conversation.objects.filter(contact_email="anna@acme.test").exists()


@pytest.mark.django_db
def test_anonymous_chat_needs_no_consent_and_contacts_stamp_it_once() -> None:
    api = APIClient()
    assert _start_chat(api).status_code == 201
    conv = Conversation.objects.get()
    assert conv.pdn_consent_at is None

    assert _start_chat(api, contact_email="anna@acme.test", pdn_consent=True).status_code == 201
    conv.refresh_from_db()
    assert conv.contact_email == "anna@acme.test"
    assert conv.pdn_consent_at is not None

    # Same thread already consented — a name update needs no second tick.
    assert _start_chat(api, display_name="Анна").status_code == 201
    conv.refresh_from_db()
    assert conv.display_name == "Анна"


@pytest.mark.django_db
@override_settings(PDN_POLICY_VERSION="2026-10-09")
def test_admin_shows_consent_on_lead_card(client) -> None:
    client.post("/api/leads/", data={**_LEAD, "pdn_consent": True}, content_type="application/json")
    lead = Lead.objects.get()
    admin = User.objects.create_superuser("pdn-admin", "pdn@hoocon.ru", "x" * 12)
    client.force_login(admin)
    page = client.get(f"/admin/leads/lead/{lead.pk}/change/")
    assert page.status_code == 200
    body = page.content.decode()
    assert "Согласие на обработку ПДн" in body
    assert "2026-10-09" in body
