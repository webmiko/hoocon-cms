"""Tests for the client cabinet API (``/api/auth/*`` + ``/api/account/*``).

Covers: registration/login (mode A), OTP login (mode B), session isolation
(staff users ≠ client accounts), owner scoping (foreign ids → 404), spec
CRUD, repeat-lead, document download, quote PDF.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from accounts.models import ClientAccount
from cabinet.models import Order, RmaCase, SpecList
from cabinet.services import _otp_key
from config.admin_otp import hash_otp_code
from crm.models import Client, ClientDocument, DocumentKind, Quote, QuoteStatus
from leads.models import Lead

_PASSWORD = "sup3r-secret!"


@pytest.fixture(autouse=True)
def _cabinet_flag_on(db: None) -> None:
    """Кабинет тестируется при включённом флаге (SiteSettings.cabinet_enabled)."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    if not site.cabinet_enabled:
        site.cabinet_enabled = True
        site.save()


def _register(client: APIClient, email: str = "buyer@acme.test") -> APIClient:
    """Register a client account via the API; returns the session client."""
    response = client.post(
        "/api/auth/register/",
        {
            "email": email,
            "password": _PASSWORD,
            "name": "Покупатель",
            "website": "",
            "form_start_ts": time.time() - 10,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return client


@pytest.mark.django_db
def test_cabinet_flag_off_404s_entire_surface() -> None:
    """cabinet_enabled=False глушит /api/auth/* + /api/account/* одним 404."""
    from sitesettings.models import SiteSettings

    site = SiteSettings.load()
    site.cabinet_enabled = False
    site.save()

    api = APIClient()
    login = api.post(
        "/api/auth/login/",
        {"email": "buyer@acme.test", "password": _PASSWORD},
        format="json",
    )
    assert login.status_code == 404
    assert api.get("/api/auth/me/").status_code == 404
    assert api.get("/api/account/me/").status_code == 404
    assert api.get("/api/account/leads/").status_code == 404


@pytest.mark.django_db
def test_register_creates_account_and_links_client() -> None:
    """POST /api/auth/register/ creates account + CRM card linked both ways."""
    api = APIClient()
    _register(api)
    account = ClientAccount.objects.get(email="buyer@acme.test")
    assert account.check_password(_PASSWORD)
    client = Client.objects.get(email="buyer@acme.test")
    assert client.account_id == account.pk

    me = api.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["email"] == "buyer@acme.test"


@pytest.mark.django_db
def test_register_honeypot_rejects_fast_bot() -> None:
    """Submissions faster than the min-fill threshold are rejected."""
    api = APIClient()
    response = api.post(
        "/api/auth/register/",
        {"email": "bot@acme.test", "password": _PASSWORD, "form_start_ts": time.time()},
        format="json",
    )
    assert response.status_code == 400
    assert not ClientAccount.objects.filter(email="bot@acme.test").exists()


@pytest.mark.django_db
def test_register_duplicate_email_rejected() -> None:
    """Second registration with the same email fails uniformly."""
    api = APIClient()
    _register(api)
    api2 = APIClient()
    response = api2.post(
        "/api/auth/register/",
        {
            "email": "buyer@acme.test",
            "password": _PASSWORD,
            "form_start_ts": time.time() - 10,
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_password_login_and_logout() -> None:
    """Mode A: password login → session; logout drops it."""
    api = APIClient()
    _register(api)
    api.post("/api/auth/logout/")
    assert api.get("/api/auth/me/").status_code == 401

    bad = api.post(
        "/api/auth/login/",
        {"email": "buyer@acme.test", "password": "wrong-pass"},
        format="json",
    )
    assert bad.status_code == 400

    ok = api.post(
        "/api/auth/login/",
        {"email": "buyer@acme.test", "password": _PASSWORD},
        format="json",
    )
    assert ok.status_code == 200
    assert api.get("/api/auth/me/").status_code == 200


@pytest.mark.django_db
def test_otp_flow_logs_in_and_verifies_email() -> None:
    """Mode B: start → verify → session; email marked verified."""
    api = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay") as send:
        response = api.post(
            "/api/auth/otp/start/",
            {"email": "otp@acme.test", "form_start_ts": time.time() - 10},
            format="json",
        )
    assert response.status_code == 200, response.content
    challenge_id = response.json()["challenge_id"]
    assert send.called

    # Inject a known code into the cached challenge (test-only path).
    payload = cache.get(_otp_key(challenge_id))
    assert payload and payload["code_hash"]
    cache.set(
        _otp_key(challenge_id),
        {**payload, "code_hash": hash_otp_code("424242")},
        timeout=300,
    )
    verify = api.post(
        "/api/auth/otp/verify/",
        {"challenge_id": challenge_id, "code": "424242"},
        format="json",
    )
    assert verify.status_code == 200, verify.content
    account = ClientAccount.objects.get(email="otp@acme.test")
    assert account.email_verified_at is not None
    # Single-use: second verify of the same challenge fails.
    again = api.post(
        "/api/auth/otp/verify/",
        {"challenge_id": challenge_id, "code": "424242"},
        format="json",
    )
    assert again.status_code == 400


@pytest.mark.django_db
def test_otp_wrong_code_rejected() -> None:
    """Wrong code → 400; attempts counted."""
    api = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        response = api.post(
            "/api/auth/otp/start/",
            {"email": "otp2@acme.test", "form_start_ts": time.time() - 10},
            format="json",
        )
    challenge_id = response.json()["challenge_id"]
    bad = api.post(
        "/api/auth/otp/verify/",
        {"challenge_id": challenge_id, "code": "000000"},
        format="json",
    )
    assert bad.status_code == 400


@pytest.mark.django_db
def test_staff_session_does_not_open_cabinet() -> None:
    """A logged-in staff User is not a client — cabinet stays 401/403."""
    staff = User.objects.create_user("mgr", password="x", is_staff=True)
    api = APIClient()
    api.force_login(staff)
    assert api.get("/api/auth/me/").status_code == 401
    assert api.get("/api/account/summary/").status_code in (401, 403)


@pytest.mark.django_db
def test_cabinet_endpoints_require_client_session() -> None:
    """Anonymous → 401/403 on every cabinet endpoint."""
    api = APIClient()
    for url in (
        "/api/account/me/",
        "/api/account/summary/",
        "/api/account/leads/",
        "/api/account/specs/",
        "/api/account/quotes/",
        "/api/account/documents/",
        "/api/account/orders/",
        "/api/account/conversations/",
        "/api/account/company/",
        "/api/account/rma/",
    ):
        assert api.get(url).status_code in (401, 403), url


def _client_with_data(email: str = "owner@acme.test") -> Client:
    """Client card with a lead, issued quote, order and document."""
    client = Client.objects.create(name="Владелец", email=email, company="Акме")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Владелец",
        email=email,
        client=client,
        message="Нужны приводы",
    )
    quote = Quote.objects.create(client=client, lead=lead, status=QuoteStatus.SENT)
    Order.objects.create(client=client, quote=quote, number="З-1")
    ClientDocument.objects.create(
        client=client,
        kind=DocumentKind.INVOICE,
        title="Счёт-1.pdf",
    )
    return client


@pytest.mark.django_db
def test_leads_scoped_to_owner() -> None:
    """Account sees only own leads; foreign lead id → 404."""
    own = _client_with_data("owner@acme.test")
    other = _client_with_data("stranger@acme.test")
    foreign_lead = other.leads.first()

    api = APIClient()
    _register(api, "owner@acme.test")
    response = api.get("/api/account/leads/")
    assert response.status_code == 200
    body = response.json()
    rows = body["results"] if isinstance(body, dict) else body
    assert [r["id"] for r in rows] == [own.leads.first().pk]
    assert api.get(f"/api/account/leads/{foreign_lead.pk}/").status_code == 404


@pytest.mark.django_db
def test_repeat_lead_idempotent() -> None:
    """POST repeat clones items; second call within the window reuses it."""
    client = _client_with_data("rep@acme.test")
    source = client.leads.first()
    assert source is not None
    api = APIClient()
    _register(api, "rep@acme.test")
    first = api.post(f"/api/account/leads/{source.pk}/repeat/")
    assert first.status_code == 201
    second = api.post(f"/api/account/leads/{source.pk}/repeat/")
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


@pytest.mark.django_db
def test_specs_crud_and_to_lead() -> None:
    """Spec create/list/patch/delete + push-to-lead."""
    api = APIClient()
    _register(api, "spec@acme.test")
    created = api.post(
        "/api/account/specs/",
        {"name": "Объект А", "items": [{"sku_code": "HVA-5NM", "quantity": 3}]},
        format="json",
    )
    assert created.status_code == 201, created.content
    spec_id = created.json()["id"]
    assert SpecList.objects.get(pk=spec_id).items.count() == 1

    pushed = api.post(f"/api/account/specs/{spec_id}/to_lead/")
    assert pushed.status_code == 201
    lead = Lead.objects.get(pk=pushed.json()["id"])
    assert lead.items.count() == 1

    other = APIClient()
    _register(other, "spec2@acme.test")
    assert other.get(f"/api/account/specs/{spec_id}/").status_code == 404
    assert other.delete(f"/api/account/specs/{spec_id}/").status_code == 404


@pytest.mark.django_db
def test_quotes_and_documents_scoped() -> None:
    """Issued quotes + documents visible; drafts hidden; foreign → 404."""
    client = _client_with_data("docs@acme.test")
    Quote.objects.create(client=client, status=QuoteStatus.DRAFT)
    foreign = _client_with_data("docs2@acme.test")
    foreign_doc = foreign.documents.first()

    api = APIClient()
    _register(api, "docs@acme.test")
    quotes = api.get("/api/account/quotes/")
    assert quotes.status_code == 200
    assert len(quotes.json()) == 1  # draft excluded
    docs = api.get("/api/account/documents/")
    assert len(docs.json()) == 1
    assert api.get(f"/api/account/documents/{foreign_doc.pk}/download/").status_code == 404


@pytest.mark.django_db
def test_orders_scoped_and_rma_owner_check() -> None:
    """Orders listed only for owner; RMA rejects a foreign order id."""
    own = _client_with_data("ord@acme.test")
    foreign = _client_with_data("ord2@acme.test")
    foreign_order = foreign.orders.first()

    api = APIClient()
    _register(api, "ord@acme.test")
    orders = api.get("/api/account/orders/")
    assert len(orders.json()) == 1
    assert orders.json()[0]["number"] == "З-1"

    bad = api.post(
        "/api/account/rma/",
        {"subject": "Не работает", "order": foreign_order.pk},
        format="json",
    )
    assert bad.status_code == 400

    ok = api.post(
        "/api/account/rma/",
        {"subject": "Гудит", "serial_number": "SN-42"},
        format="json",
    )
    assert ok.status_code == 201
    assert RmaCase.objects.get(pk=ok.json()["id"]).client_id == own.pk


@pytest.mark.django_db
def test_summary_counts_own_objects() -> None:
    """Summary reflects only the session client's rows."""
    _client_with_data("sum@acme.test")
    api = APIClient()
    _register(api, "sum@acme.test")
    summary = api.get("/api/account/summary/")
    assert summary.status_code == 200
    assert summary.json()["active_leads"] == 1
    assert summary.json()["quotes_pending"] == 1
    assert summary.json()["orders_in_work"] == 1


@pytest.mark.django_db
def test_quote_pdf_endpoint_owner_only() -> None:
    """PDF renders for own issued quote; foreign/draft → 404."""
    client = _client_with_data("pdf@acme.test")
    quote = client.quotes.first()
    foreign = _client_with_data("pdf2@acme.test").quotes.first()

    api = APIClient()
    _register(api, "pdf@acme.test")
    response = api.get(f"/api/account/quotes/{quote.pk}/pdf/")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert api.get(f"/api/account/quotes/{foreign.pk}/pdf/").status_code == 404


@pytest.mark.django_db
def test_documents_zip_owner_only() -> None:
    """ZIP export streams own documents under their titles."""
    import io
    import zipfile

    from django.core.files.base import ContentFile

    client = _client_with_data("zip@acme.test")
    doc = client.documents.first()
    assert doc is not None
    doc.file.save("invoice.pdf", ContentFile(b"%PDF-1.4 zip-test"))

    api = APIClient()
    _register(api, "zip@acme.test")
    response = api.get("/api/account/documents/zip/")
    assert response.status_code == 200
    buf = io.BytesIO(b"".join(response.streaming_content))
    with zipfile.ZipFile(buf) as zf:
        assert zf.namelist() == ["Счёт-1.pdf"]


@pytest.mark.django_db
def test_account_inactive_denied() -> None:
    """Deactivated account session is dropped → 401."""
    api = APIClient()
    _register(api, "off@acme.test")
    ClientAccount.objects.filter(email="off@acme.test").update(is_active=False)
    assert api.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
def test_rma_photo_upload_and_owner_download() -> None:
    """Multipart RMA accepts a defect photo; owner-only download (ЛК-12)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    # 1x1 px PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    api = APIClient()
    _register(api, "rma-photo@acme.test")
    created = api.post(
        "/api/account/rma/",
        {
            "subject": "Скрип",
            "photo": SimpleUploadedFile("defect.png", png, content_type="image/png"),
        },
        format="multipart",
    )
    assert created.status_code == 201, created.content
    case_id = created.json()["id"]
    assert created.json()["has_photo"] is True
    assert RmaCase.objects.get(pk=case_id).photo.name.endswith(".png")

    photo = api.get(f"/api/account/rma/{case_id}/photo/")
    assert photo.status_code == 200

    other = APIClient()
    _register(other, "rma-photo2@acme.test")
    assert other.get(f"/api/account/rma/{case_id}/photo/").status_code == 404


@pytest.mark.django_db
def test_session_mutation_requires_csrf() -> None:
    """Session PATCH without X-CSRFToken → 403; with token → 200.

    Regression: cabinet sessions must enforce CSRF like staff sessions —
    ClientSessionAuthentication wires enforce_csrf into every view via
    ClientApiView (cookie auth without it would accept cross-site POSTs).
    """
    api = APIClient(enforce_csrf_checks=True)
    api.get("/api/csrf/")
    _register(api, "csrf-check@acme.test")
    # Без CSRF-заголовка → 403 даже с валидной сессией.
    denied = api.patch("/api/account/me/", {"name": "X"}, format="json")
    assert denied.status_code == 403
    # GET (безопасный метод) без токена — ок.
    assert api.get("/api/account/me/").status_code == 200
    token = api.cookies.get("csrftoken")
    assert token is not None
    ok = api.patch(
        "/api/account/me/",
        {"name": "С Токеном"},
        format="json",
        HTTP_X_CSRFTOKEN=token.value,
    )
    assert ok.status_code == 200
