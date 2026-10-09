"""Tests for the client cabinet API (``/api/auth/*`` + ``/api/account/*``).

Covers: registration/login (mode A), OTP login (mode B), session isolation
(staff users ≠ client accounts), owner scoping (foreign ids → 404), spec
CRUD, repeat-lead, document download, quote PDF.
"""

from __future__ import annotations

import time
from typing import Any
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


def _start_registration(client: APIClient, email: str) -> str:
    """POST /api/auth/register/ → challenge id (no account yet)."""
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        response = client.post(
            "/api/auth/register/",
            {
                "pdn_consent": True,
                "email": email,
                "password": _PASSWORD,
                "name": "Покупатель",
                "website": "",
                "form_start_ts": time.time() - 10,
            },
            format="json",
        )
    assert response.status_code == 202, response.content
    return response.json()["challenge_id"]


def _verify(client: APIClient, challenge_id: str, code: str = "424242") -> None:
    """Swap a known code into the cached challenge and verify it."""
    payload = cache.get(_otp_key(challenge_id))
    cache.set(_otp_key(challenge_id), {**payload, "code_hash": hash_otp_code(code)}, timeout=300)
    response = client.post("/api/auth/otp/verify/", {"challenge_id": challenge_id, "code": code}, format="json")
    assert response.status_code == 200, response.content


def _register(client: APIClient, email: str = "buyer@acme.test") -> APIClient:
    """Register + confirm the emailed code; returns the session client."""
    _verify(client, _start_registration(client, email))
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
    """Register + code → verified password account and CRM card linked both ways."""
    api = APIClient()
    _register(api)
    account = ClientAccount.objects.get(email="buyer@acme.test")
    assert account.check_password(_PASSWORD)
    assert account.email_verified_at is not None
    client = Client.objects.get(email="buyer@acme.test")
    assert client.account_id == account.pk

    me = api.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["email"] == "buyer@acme.test"


@pytest.mark.django_db
def test_register_with_foreign_email_exposes_nothing_until_code() -> None:
    """Регистрация на чужую почту открывала CRM-карточку владельца без подтверждения.

    Root invariant: no ClientAccount and no card link exist before the code
    from the letter is entered; the register call itself grants no session.
    """
    victim = _client_with_data("victim@acme.test")
    attacker = APIClient()
    _start_registration(attacker, "victim@acme.test")

    assert not ClientAccount.objects.filter(email="victim@acme.test").exists()
    victim.refresh_from_db()
    assert victim.account_id is None
    assert attacker.get("/api/auth/me/").status_code == 401
    assert attacker.get("/api/account/leads/").status_code in (401, 403)


def _verified_account(email: str) -> ClientAccount:
    from django.utils import timezone

    account = ClientAccount(email=email, email_verified_at=timezone.now())
    account.set_password(_PASSWORD)
    account.save()
    return account


@pytest.mark.django_db
def test_anonymous_login_requires_csrf_token() -> None:
    """Login CSRF: чужая страница не может залогинить жертву в аккаунт атакующего."""
    _verified_account("attacker@acme.test")
    api = APIClient(enforce_csrf_checks=True)
    payload = {"email": "attacker@acme.test", "password": _PASSWORD}

    forged = api.post("/api/auth/login/", payload, format="json")
    assert forged.status_code == 403
    assert api.get("/api/auth/me/").status_code == 401

    token = api.get("/api/csrf/").json()["csrfToken"]
    ok = api.post("/api/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)
    assert ok.status_code == 200, ok.content


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/register/",
        "/api/auth/login/",
        "/api/auth/otp/start/",
        "/api/auth/otp/verify/",
        "/api/auth/otp/resend/",
    ],
)
def test_auth_endpoints_reject_form_bodies(path: str) -> None:
    """/api/auth/* принимает только JSON: кросс-сайтовая HTML-форма получает 415."""
    response = APIClient().post(path, {"email": "a@acme.test"}, format="multipart")
    assert response.status_code == 415


@pytest.mark.django_db
def test_unverified_legacy_account_cannot_read_cabinet() -> None:
    """Аккаунт без подтверждённой почты (старая регистрация) не видит кабинет и не входит паролем."""
    _client_with_data("legacy@acme.test")
    account = ClientAccount(email="legacy@acme.test")
    account.set_password(_PASSWORD)
    account.save()
    api = APIClient()

    login = api.post("/api/auth/login/", {"email": "legacy@acme.test", "password": _PASSWORD}, format="json")
    assert login.status_code == 400

    session = api.session
    session["client_account_id"] = account.pk
    session.save()
    assert api.get("/api/account/leads/").status_code == 403


@pytest.mark.django_db
def test_code_login_drops_password_set_before_verification() -> None:
    """Пароль, заданный до подтверждения почты, не переживает вход владельца по коду."""
    account = ClientAccount(email="owner2@acme.test")
    account.set_password("attacker-pass")
    account.save()
    api = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        start = api.post(
            "/api/auth/otp/start/",
            {"pdn_consent": True, "email": "owner2@acme.test", "form_start_ts": time.time() - 10},
            format="json",
        )
    _verify(api, start.json()["challenge_id"])

    account.refresh_from_db()
    assert account.email_verified_at is not None
    assert not account.check_password("attacker-pass")


@pytest.mark.django_db
def test_otp_start_creates_no_account_or_card() -> None:
    """Запрос кода на любую почту не создаёт аккаунт и CRM-карточку."""
    api = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        response = api.post(
            "/api/auth/otp/start/",
            {"pdn_consent": True, "email": "spam@acme.test", "form_start_ts": time.time() - 10},
            format="json",
        )
    assert response.status_code == 200
    assert not ClientAccount.objects.filter(email="spam@acme.test").exists()
    assert not Client.objects.filter(email="spam@acme.test").exists()


@pytest.mark.django_db
def test_otp_quota_exceeded_returns_429(settings) -> None:
    """Превышение квоты отправки кодов давало 500 вместо 429."""
    settings.CLIENT_OTP_REQUEST_LIMIT = 1
    api = APIClient()
    payload = {"pdn_consent": True, "email": "quota@acme.test", "form_start_ts": time.time() - 10}
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        assert api.post("/api/auth/otp/start/", payload, format="json").status_code == 200
        second = api.post("/api/auth/otp/start/", payload, format="json")
    assert second.status_code == 429
    assert second.json()["detail"]


@pytest.mark.django_db
def test_honeypot_rejects_missing_form_timestamp() -> None:
    """Без form_start_ts honeypot пропускал запрос (elapsed = эпоха Unix)."""
    api = APIClient()
    response = api.post("/api/auth/otp/start/", {"pdn_consent": True, "email": "bot2@acme.test"}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_otp_attempts_counter_is_atomic_and_caps_guesses(settings) -> None:
    """Счётчик попыток — отдельный атомарный ключ; после лимита задание удаляется."""
    settings.CLIENT_OTP_MAX_ATTEMPTS = 2  # read via otp_max_attempts("CLIENT_OTP")
    api = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        start = api.post(
            "/api/auth/otp/start/",
            {"pdn_consent": True, "email": "guess@acme.test", "form_start_ts": time.time() - 10},
            format="json",
        )
    challenge_id = start.json()["challenge_id"]
    for _ in range(2):
        bad = api.post("/api/auth/otp/verify/", {"challenge_id": challenge_id, "code": "000000"}, format="json")
        assert bad.status_code == 400
    assert cache.get(_otp_key(challenge_id)) is None


@pytest.mark.django_db
def test_register_honeypot_rejects_fast_bot() -> None:
    """Submissions faster than the min-fill threshold are rejected."""
    api = APIClient()
    response = api.post(
        "/api/auth/register/",
        {"pdn_consent": True, "email": "bot@acme.test", "password": _PASSWORD, "form_start_ts": time.time()},
        format="json",
    )
    assert response.status_code == 400
    assert not ClientAccount.objects.filter(email="bot@acme.test").exists()


@pytest.mark.django_db
def test_register_duplicate_email_same_response_keeps_password() -> None:
    """Повторная регистрация на занятую почту: тот же ответ (без перебора), пароль не меняется."""
    api = APIClient()
    _register(api)
    api2 = APIClient()
    with patch("cabinet.tasks.send_client_otp_email_task.delay"):
        response = api2.post(
            "/api/auth/register/",
            {
                "pdn_consent": True,
                "email": "buyer@acme.test",
                "password": "other-password",
                "form_start_ts": time.time() - 10,
            },
            format="json",
        )
    assert response.status_code == 202
    assert set(response.json()) == {"challenge_id", "email_masked"}
    payload = cache.get(_otp_key(response.json()["challenge_id"]))
    assert payload["pending"] is None
    assert ClientAccount.objects.get(email="buyer@acme.test").check_password(_PASSWORD)


@pytest.mark.django_db
def test_logout_rotates_session_and_drops_support_chat() -> None:
    """После выхода чат и id сессии переживали logout — следующий посетитель видел переписку."""
    from django.conf import settings

    from supportchat.services import SESSION_KEY as SUPPORT_SESSION_KEY

    api = APIClient()
    _register(api)
    session = api.session
    session[SUPPORT_SESSION_KEY] = "chat-of-buyer"
    session.save()
    old_key = api.cookies[settings.SESSION_COOKIE_NAME].value

    assert api.post("/api/auth/logout/").status_code == 204

    new_key = api.cookies[settings.SESSION_COOKIE_NAME].value
    assert new_key != old_key
    assert SUPPORT_SESSION_KEY not in api.session
    assert api.get("/api/auth/me/").status_code == 401


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
            {"pdn_consent": True, "email": "otp@acme.test", "form_start_ts": time.time() - 10},
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
            {"pdn_consent": True, "email": "otp2@acme.test", "form_start_ts": time.time() - 10},
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


@pytest.mark.django_db
def test_company_requisites_hidden_until_manager_confirms_member() -> None:
    """Посторонний с тем же названием компании не видит ИНН, адрес и сотрудников."""
    from crm.models import Company, CompanyMember

    owner = Client.objects.create(name="Директор", email="boss@acme.test", company="Акме")
    org = Company.objects.get(pk=owner.company_ref_id)
    org.inn = "7700000000"
    org.legal_address = "Москва, ул. Тайная, 1"
    org.save()
    CompanyMember.objects.filter(company=org, client=owner).update(is_confirmed=True)

    api = _register(APIClient(), "stranger@evil.test")
    stranger = Client.objects.get(email="stranger@evil.test")
    stranger.company = "АКМЕ"
    stranger.save()
    stranger.refresh_from_db()
    assert stranger.company_ref_id == org.pk
    assert CompanyMember.objects.get(company=org, client=stranger).is_confirmed is False

    data = api.get("/api/account/company/").json()
    assert data["confirmed"] is False
    assert data["inn"] == ""
    assert data["legal_address"] == ""
    assert data["members"] == []

    CompanyMember.objects.filter(company=org, client=stranger).update(is_confirmed=True)
    data = api.get("/api/account/company/").json()
    assert data["confirmed"] is True
    assert data["inn"] == "7700000000"
    assert len(data["members"]) == 2


def _post_public_lead(api: APIClient, email: str, message: str) -> Lead:
    with (
        patch("leads.lifecycle.send_lead_notification.delay"),
        patch("leads.lifecycle.send_lead_client_confirmation.delay"),
    ):
        resp = api.post(
            "/api/leads/",
            {
                "pdn_consent": True,
                "lead_type": "consultation",
                "name": "Кто-то",
                "company": "ООО Ромашка",
                "email": email,
                "message": f"{message} — подробности в письме",
                "website": "",
            },
            format="json",
        )
    assert resp.status_code == 201, resp.content
    return Lead.objects.get(pk=resp.json()["id"])


def _cabinet_lead_ids(api: APIClient) -> list[int]:
    body = api.get("/api/account/leads/").json()
    rows = body["results"] if isinstance(body, dict) else body
    return [row["id"] for row in rows]


@pytest.mark.django_db
def test_foreign_anonymous_lead_hidden_until_contact_confirmed() -> None:
    """M8: аноним с чужим email не подкидывает заявку в кабинет жертвы — даже после взятия в работу."""
    victim = _register(APIClient(), "victim@acme.test")
    forged = _post_public_lead(APIClient(), "victim@acme.test", "Срочно оплатите по ссылке evil.test")
    assert forged.client_id == Client.objects.get(email="victim@acme.test").pk
    assert forged.contact_verified is False

    assert forged.pk not in _cabinet_lead_ids(victim)
    assert victim.get(f"/api/account/leads/{forged.pk}/").status_code == 404
    assert victim.get("/api/account/summary/").json()["active_leads"] == 0

    from leads.services import take_lead_in_work

    manager = User.objects.create_user("m8-mgr", password="x", is_staff=True)
    take_lead_in_work(forged, manager)
    assert forged.pk not in _cabinet_lead_ids(victim)
    assert victim.get(f"/api/account/leads/{forged.pk}/").status_code == 404

    Lead.objects.filter(pk=forged.pk).update(contact_verified=True)
    assert forged.pk in _cabinet_lead_ids(victim)


@pytest.mark.django_db
def test_foreign_web_chat_hidden_after_manager_reply() -> None:
    """M8: ответ менеджера не делает чужой диалог видимым в кабинете владельца почты."""
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    from supportchat.models import Message, MessageDirection
    from supportchat.services import start_or_resume_web_conversation

    victim = _register(APIClient(), "chat-victim@acme.test")
    request = RequestFactory().post("/api/support/start/")
    request.session = SessionStore()
    forged = start_or_resume_web_conversation(request, contact_email="chat-victim@acme.test", pdn_consent=True)
    manager = User.objects.create_user("m8-chat-mgr", password="x", is_staff=True)
    Message.objects.create(
        conversation=forged,
        direction=MessageDirection.OUTBOUND,
        author=manager,
        body="Отправьте реквизиты",
    )

    assert victim.get("/api/account/conversations/").json() == []
    assert victim.get("/api/account/summary/").json()["unread_conversations"] == 0


@pytest.mark.django_db
def test_lead_from_signed_in_owner_is_verified_immediately() -> None:
    """Заявка с сайта от вошедшего владельца почты видна в кабинете сразу."""
    owner = _register(APIClient(), "self@acme.test")
    lead = _post_public_lead(owner, "self@acme.test", "Мой вопрос")
    assert lead.contact_verified is True
    assert lead.pk in _cabinet_lead_ids(owner)

    other = _post_public_lead(owner, "someone-else@acme.test", "Для коллеги")
    assert other.contact_verified is False


@pytest.mark.django_db
def test_sent_quote_confirms_lead_contact() -> None:
    """Отправленное менеджером КП подтверждает контакт заявки."""
    from crm.quote_ops import finalize_quote_status

    lead = _post_public_lead(APIClient(), "kp@acme.test", "Нужно КП")
    quote = Quote.objects.create(client=lead.client, lead=lead, status=QuoteStatus.SENT)
    manager = User.objects.create_user("kp-mgr", password="x", is_staff=True)
    with patch("crm.quote_docs.ensure_quote_pdf_document", return_value=None):
        finalize_quote_status(quote, actor=manager)
    lead.refresh_from_db()
    assert lead.contact_verified is True


@pytest.mark.django_db
def test_web_chat_contact_verified_only_for_owner_session() -> None:
    """Диалог с чужим email скрыт; начатый из кабинета той же почтой — подтверждён."""
    from django.test import RequestFactory

    from cabinet.auth import login_client
    from supportchat.services import start_or_resume_web_conversation

    account = _verified_account("chat@acme.test")
    factory = RequestFactory()

    def _request(signed_in: bool) -> Any:
        from django.contrib.sessions.backends.db import SessionStore

        request = factory.post("/api/support/start/")
        request.session = SessionStore()
        if signed_in:
            login_client(request, account)
        return request

    stranger = start_or_resume_web_conversation(_request(False), contact_email="chat@acme.test", pdn_consent=True)
    assert stranger.contact_verified is False
    owner = start_or_resume_web_conversation(_request(True), contact_email="chat@acme.test", pdn_consent=True)
    assert owner.contact_verified is True

    api = _register(APIClient(), "chat2@acme.test")
    hidden = start_or_resume_web_conversation(_request(False), contact_email="chat2@acme.test", pdn_consent=True)
    assert hidden.client_id is not None
    assert api.get("/api/account/conversations/").json() == []


def _client_with_data(email: str = "owner@acme.test") -> Client:
    """Client card with a lead, issued quote, order and document."""
    client = Client.objects.create(name="Владелец", email=email, company="Акме")
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Владелец",
        email=email,
        client=client,
        contact_verified=True,
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
def test_repeat_dedup_does_not_match_longer_lead_number() -> None:
    """M10: повтор #1 не должен вернуть недавний повтор #12 (message__contains)."""
    client = _client_with_data("prefix@acme.test")
    api = _register(APIClient(), "prefix@acme.test")
    short = client.leads.first()
    assert short is not None
    repeat_of_longer = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="x",
        email=client.email,
        client=client,
        contact_verified=True,
        message=f"Повтор заявки #{short.pk}2",
    )

    repeat_of_short = api.post(f"/api/account/leads/{short.pk}/repeat/")
    assert repeat_of_short.status_code == 201
    assert repeat_of_short.json()["id"] != repeat_of_longer.pk
    assert repeat_of_short.json()["message"] == f"Повтор заявки #{short.pk}"


@pytest.mark.django_db
def test_cabinet_leads_notify_and_route_like_site_form(django_capture_on_commit_callbacks: Any) -> None:
    """M11: повтор и заявка из спецификации проходят тот же on_lead_created, что форма сайта."""
    client = _client_with_data("route@acme.test")
    source = client.leads.first()
    assert source is not None
    api = _register(APIClient(), "route@acme.test")
    spec = SpecList.objects.create(account=ClientAccount.objects.get(email="route@acme.test"), name="Склад")
    spec.items.create(sku_code="DA2-MU", quantity=2, position=0)

    with (
        patch("leads.lifecycle.send_lead_notification") as sales,
        patch("leads.lifecycle.send_lead_client_confirmation") as confirm,
        patch("leads.lifecycle._enqueue_staff_push") as push,
        patch("leads.lifecycle.assign_lead_on_create") as assign,
        django_capture_on_commit_callbacks(execute=True),
    ):
        repeat = api.post(f"/api/account/leads/{source.pk}/repeat/")
        from_spec = api.post(f"/api/account/specs/{spec.pk}/to_lead/")
    assert repeat.status_code == 201
    assert from_spec.status_code == 201, from_spec.content
    created = {repeat.json()["id"], from_spec.json()["id"]}
    assert {c.args[0].pk for c in assign.call_args_list} == created
    assert {c.args[0] for c in sales.delay.call_args_list} == created
    assert {c.args[0] for c in confirm.delay.call_args_list} == created
    assert {c.args[0] for c in push.call_args_list} == created


@pytest.mark.django_db
def test_rma_notifies_card_owner(django_capture_on_commit_callbacks: Any, mailoutbox: Any) -> None:
    """M11: рекламация из кабинета уходит письмом владельцу карточки."""
    from cabinet.tasks import notify_staff_new_rma

    owner = User.objects.create_user("rma-mgr", email="mgr@hoocon.test", password="x", is_staff=True)
    client = _client_with_data("rma@acme.test")
    client.assignee = owner
    client.save()
    api = _register(APIClient(), "rma@acme.test")
    with (
        patch("cabinet.tasks.notify_staff_new_rma.delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        resp = api.post("/api/account/rma/", {"subject": "Гудит привод", "serial_number": "SN-7"}, format="json")
    assert resp.status_code == 201
    case_id = resp.json()["id"]
    delay.assert_called_once_with(case_id)

    notify_staff_new_rma.apply(args=[case_id])
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["mgr@hoocon.test"]
    assert f"Рекламация #{case_id}" in mailoutbox[0].subject
    assert "SN-7" in mailoutbox[0].body


@pytest.mark.django_db
def test_cabinet_reads_do_not_relink_card() -> None:
    """M12: GET кабинета читает Client по account, без get_or_create/SELECT FOR UPDATE."""
    api = _register(APIClient(), "fast@acme.test")
    with patch("cabinet.views.link_client_account") as relink:
        for url in ("/api/account/summary/", "/api/account/leads/", "/api/account/quotes/"):
            assert api.get(url).status_code == 200
    relink.assert_not_called()


@pytest.mark.django_db
def test_lead_detail_hides_draft_quotes() -> None:
    """M9: деталь заявки не отдаёт черновики КП (как и список КП)."""
    client = _client_with_data("drafts@acme.test")
    lead = client.leads.first()
    assert lead is not None
    draft = Quote.objects.create(client=client, lead=lead, status=QuoteStatus.DRAFT, comment="внутренняя цена")
    api = _register(APIClient(), "drafts@acme.test")
    quotes = api.get(f"/api/account/leads/{lead.pk}/").json()["quotes"]
    ids = {q["id"] for q in quotes}
    assert draft.pk not in ids
    assert len(ids) == 1


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


def _catalog_sku(code: str, *, published: bool = True):
    from catalog.models import SKU, Category, Product

    cat, _ = Category.objects.get_or_create(name="Приводы", slug="spec-drives")
    product, _ = Product.objects.get_or_create(name="Серия", slug="spec-series", category=cat)
    return SKU.objects.create(
        product=product, sku_code=code, name=code, slug=f"spec-{code.lower()}", is_published=published
    )


@pytest.mark.django_db
def test_spec_save_with_sku_id_does_not_500() -> None:
    """«sku»: id → 500: в filter(pk=…) уходил уже разрешённый объект SKU."""
    sku = _catalog_sku("SPEC-DA24")
    api = APIClient()
    _register(api, "spec-id@acme.test")
    created = api.post(
        "/api/account/specs/",
        {"name": "По id", "items": [{"sku": sku.pk, "quantity": 2}]},
        format="json",
    )
    assert created.status_code == 201, created.content
    item = SpecList.objects.get(pk=created.json()["id"]).items.get()
    assert item.sku_id == sku.pk
    assert item.sku_code == "SPEC-DA24"
    assert item.quantity == 2


@pytest.mark.django_db
def test_spec_rejects_unpublished_sku_and_oversized_lists() -> None:
    """Неопубликованные SKU принимались (утечка каталога), число строк не ограничено."""
    from cabinet.serializers import SPEC_MAX_ITEMS

    hidden = _catalog_sku("SPEC-HIDDEN", published=False)
    api = APIClient()
    _register(api, "spec-limits@acme.test")
    by_id = api.post("/api/account/specs/", {"name": "Скрытый", "items": [{"sku": hidden.pk}]}, format="json")
    assert by_id.status_code == 400

    by_code = api.post("/api/account/specs/", {"name": "Код", "items": [{"sku_code": "spec-hidden"}]}, format="json")
    assert by_code.status_code == 201
    assert SpecList.objects.get(pk=by_code.json()["id"]).items.get().sku_id is None

    too_many = [{"sku_code": f"X-{n}"} for n in range(SPEC_MAX_ITEMS + 1)]
    big = api.post("/api/account/specs/", {"name": "Много", "items": too_many}, format="json")
    assert big.status_code == 400
    bad_qty = api.post(
        "/api/account/specs/", {"name": "Ноль", "items": [{"sku_code": "A", "quantity": 0}]}, format="json"
    )
    assert bad_qty.status_code == 400


@pytest.mark.django_db
def test_spec_rejects_quantity_beyond_int4_with_400() -> None:
    """M62: quantity > 2^31 падал 500 на INSERT в PositiveIntegerField."""
    api = APIClient()
    _register(api, "spec-huge-qty@acme.test")
    ok = api.post(
        "/api/account/specs/", {"name": "Норма", "items": [{"sku_code": "A", "quantity": 100_000}]}, format="json"
    )
    assert ok.status_code == 201, ok.content
    response = api.post(
        "/api/account/specs/", {"name": "Много", "items": [{"sku_code": "A", "quantity": 2**31}]}, format="json"
    )
    assert response.status_code == 400
    assert not SpecList.objects.filter(name="Много").exists()


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
def test_documents_zip_is_bounded_and_skips_missing_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """M34: ZIP не держится целиком в памяти, есть общий лимит и пропуск потерянных файлов."""
    import io
    import zipfile

    from django.core.files.base import ContentFile

    from cabinet import views as cabinet_views

    client = _client_with_data("zipcap@acme.test")
    doc = client.documents.first()
    assert doc is not None
    doc.file.save("big.pdf", ContentFile(b"%PDF-1.4 " + b"x" * 2048))
    lost = client.documents.create(title="Потерянный.pdf", kind=doc.kind)
    lost.file.name = "client_docs/missing-on-disk.pdf"
    lost.save(update_fields=["file"])

    api = APIClient()
    _register(api, "zipcap@acme.test")
    response = api.get("/api/account/documents/zip/")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content))) as zf:
        names = zf.namelist()
    assert len(names) == 1
    assert not any("Потерянный" in name for name in names)

    monkeypatch.setattr(cabinet_views, "DOCUMENTS_ZIP_MAX_BYTES", 1024)
    too_big = api.get("/api/account/documents/zip/")
    assert too_big.status_code == 413
    assert "по отдельности" in too_big.json()["detail"]


def test_documents_zip_has_own_throttle() -> None:
    """M34: тяжёлый ZIP — отдельный throttle, а не общий лимит кабинета."""
    from django.conf import settings

    from cabinet.views import AccountDocumentsZipView

    assert AccountDocumentsZipView.throttle_scope == "client_zip"
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["client_zip"]


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
    registered = _register(APIClient(), "csrf-check@acme.test")
    api = APIClient(enforce_csrf_checks=True)
    api.cookies = registered.cookies
    api.get("/api/csrf/")
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
