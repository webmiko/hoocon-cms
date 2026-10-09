"""E2E-прогон клиентского маршрута: заявка → карточка → переписка → звонок → КП → кабинет.

Один сквозной сценарий проверяет, что каждый шаг сохраняется в БД,
привязывается к карточке клиента и виден там, где должен:

- менеджеру — в админке (Activity, Call, EmailMessage, Quote, ClientDocument);
- клиенту — в кабинете (``/api/account/*``, owner-scoped).

Цепочка: POST /api/leads/ → авто-создание карточки (crm/signals) → ответ
менеджера (EmailMessage + Activity) → Mango-звонок (Call + Activity) →
КП из заявки → выдача через реальный admin-save → PDF-документ →
регистрация кабинета той же почтой → видимость данных → изоляция.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.test import Client as DjangoClient
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import ClientAccount, StaffVpbxProfile
from crm.models import (
    Activity,
    ActivityType,
    Call,
    CallState,
    Client,
    ClientDocument,
    DocumentKind,
    EmailMessage,
    Quote,
    QuoteStatus,
)
from crm.services import create_lead_reply_email, create_quote_from_lead
from leads.models import Lead
from sitesettings.models import SiteSettings
from supportchat.models import (
    Channel,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
)

_PASSWORD = "sup3r-secret!"

_CLIENT_EMAIL = "ivan@acme.test"
_CLIENT_PHONE = "+7 (915) 111-22-33"


def _signed_mango_body(payload: dict[str, Any]) -> dict[str, str]:
    """Form body as Mango sends it: vpbx_api_key + json + sha256 sign."""
    raw = json.dumps(payload, ensure_ascii=False)
    sign = hashlib.sha256(f"test-key{raw}test-salt".encode()).hexdigest()
    return {"vpbx_api_key": "test-key", "json": raw, "sign": sign}


def _mango_call_payload(**over: Any) -> dict[str, Any]:
    """Inbound call: client number → manager extension 101."""
    payload: dict[str, Any] = {
        "entry_id": "e2e-entry-1",
        "call_id": "e2e-call-1",
        "timestamp": 1760000000,
        "seq": 1,
        "call_state": "Appeared",
        "location": "abonent",
        "from": {"number": "79151112233"},
        "to": {"extension": "101"},
    }
    payload.update(over)
    return payload


def _register_cabinet(api: APIClient, email: str, name: str) -> None:
    """Register in the cabinet and confirm the emailed code (account appears on verify)."""
    with patch("cabinet.tasks.send_client_otp_email_task.delay") as send:
        resp = api.post(
            "/api/auth/register/",
            {
                "pdn_consent": True,
                "email": email,
                "password": _PASSWORD,
                "name": name,
                "website": "",
                "form_start_ts": time.time() - 10,
            },
            format="json",
        )
    assert resp.status_code == 202, resp.content
    code = send.call_args.args[1]
    verify = api.post(
        "/api/auth/otp/verify/",
        {"challenge_id": resp.json()["challenge_id"], "code": code},
        format="json",
    )
    assert verify.status_code == 200, verify.content


@pytest.mark.django_db
def test_full_client_journey_lead_to_cabinet(settings: Any) -> None:
    """Сквозной маршрут: каждый артефакт сохранён и привязан к карточке."""
    settings.MANGO_VPBX_API_KEY = "test-key"
    settings.MANGO_VPBX_API_SALT = "test-salt"
    site = SiteSettings.load()
    site.cabinet_enabled = True
    site.save()

    api = APIClient()

    # ── Шаг 1: заявка с сайта → карточка клиента создаётся автоматически ──
    resp = api.post(
        "/api/leads/",
        {
            "pdn_consent": True,
            "lead_type": "rfq",
            "name": "Иван Петров",
            "email": _CLIENT_EMAIL,
            "phone": _CLIENT_PHONE,
            "company": "ООО Акме",
            "message": "Нужна цена на приводы для склада.",
            "items": [{"sku_code": "HVA-5NM", "quantity": 3}],
            "website": "",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content

    lead = Lead.objects.get()
    client = Client.objects.get(email=_CLIENT_EMAIL)
    lead.refresh_from_db()
    assert lead.client_id == client.pk, "заявка не привязана к карточке"
    assert client.phone, "карточка не подхватила телефон заявки"
    inbound = Activity.objects.get(client=client, lead=lead)
    assert inbound.activity_type == ActivityType.NOTE
    assert f"#{lead.pk}" in inbound.subject

    # ── Шаг 2: менеджер отвечает на заявку — письмо + Activity на карточке ──
    manager = User.objects.create_user(
        username="mgr",
        email="mgr@hoocon.ru",
        password="pw12345678",
        is_staff=True,
        is_superuser=True,
    )
    msg = create_lead_reply_email(
        lead=lead,
        subject="Re: заявка на приводы",
        body="Здравствуйте! Готовим КП, уточните сроки.",
        author=manager,
        reply_to_email="mgr@hoocon.ru",
        send_now=False,
    )
    assert msg.client_id == client.pk
    assert msg.lead_id == lead.pk
    mail_act = Activity.objects.get(client=client, activity_type=ActivityType.EMAIL)
    assert mail_act.lead_id == lead.pk, "письмо не привязано к заявке"
    assert mail_act.subject == "Re: заявка на приводы"

    # ── Шаг 3: входящий звонок через Mango → Call + Activity ──
    StaffVpbxProfile.objects.create(user=manager, extension="101")
    hook_url = "/api/telephony/mango/events/"
    api.post(hook_url, _signed_mango_body(_mango_call_payload(seq=1)))
    api.post(
        hook_url,
        _signed_mango_body(
            _mango_call_payload(seq=2, call_state="Connected", timestamp=1760000005),
        ),
    )
    api.post(
        hook_url,
        _signed_mango_body(
            _mango_call_payload(seq=3, call_state="Disconnected", timestamp=1760000070),
        ),
    )
    call = Call.objects.get(entry_id="e2e-entry-1")
    assert call.state == CallState.DISCONNECTED
    assert call.client_id == client.pk, "звонок не резолвлен в карточку"
    assert call.manager_id == manager.pk
    assert call.lead_id == lead.pk, "звонок не привязан к последней открытой заявке"
    call_act = Activity.objects.get(client=client, activity_type=ActivityType.CALL)
    assert call_act.lead_id == lead.pk

    # ── Шаг 4: КП из заявки → выдача через реальный admin POST ──
    quote, created = create_quote_from_lead(lead, author=manager)
    assert created and quote.status == QuoteStatus.DRAFT
    item = quote.items.get()
    assert item.sku_code == "HVA-5NM" and item.quantity == 3

    admin_client = DjangoClient()
    admin_client.force_login(manager)
    change_url = reverse("admin:crm_quote_change", args=[quote.pk])
    resp = admin_client.post(
        change_url,
        {
            "client": str(client.pk),
            "lead": str(lead.pk),
            "status": QuoteStatus.SENT,
            "comment": "",
            "created_by": str(manager.pk),
            "vat_rate": "22.00",
            "valid_until": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "1",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-id": str(item.pk),
            "items-0-sku_code": "HVA-5NM",
            "items-0-quantity": "3",
            "items-0-unit_price": "15000.00",
            "items-0-sort_order": "0",
            "_save": "Сохранить",
        },
    )
    assert resp.status_code == 302, resp.content

    quote.refresh_from_db()
    lead.refresh_from_db()
    assert quote.status == QuoteStatus.SENT
    assert quote.sent_at is not None
    assert lead.status == Lead.LeadStatus.DONE, "выданное КП не закрыло заявку"

    doc = ClientDocument.objects.get(quote=quote, kind=DocumentKind.QUOTE_PDF)
    assert doc.client_id == client.pk
    assert doc.file.name.endswith(".pdf")
    notify = EmailMessage.objects.get(client=client, subject__contains=quote.number)
    assert notify.lead_id == lead.pk

    # ── Шаг 5: диалог в чате поддержки — привязан к карточке ──
    conv = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-e2e",
        client=client,
        lead=lead,
        status=ConversationStatus.OPEN,
        display_name="Иван",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        body="Здравствуйте, когда будет КП?",
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.OUTBOUND,
        body="Уже высылаем на почту.",
        author=manager,
    )

    # ── Шаг 6: клиент регистрируется в кабинете той же почтой ──
    cab = APIClient()
    _register_cabinet(cab, _CLIENT_EMAIL, "Иван Петров")
    account = ClientAccount.objects.get(email=_CLIENT_EMAIL)
    client.refresh_from_db()
    assert client.account_id == account.pk, "аккаунт не привязан к карточке"

    # Клиент видит всю свою историю (leads — пагинированный ответ):
    leads_resp = cab.get("/api/account/leads/").json()
    leads = leads_resp["results"] if isinstance(leads_resp, dict) else leads_resp
    assert leads[0]["id"] == lead.pk
    assert leads[0]["status"] == Lead.LeadStatus.DONE

    quotes = cab.get("/api/account/quotes/").json()
    assert len(quotes) == 1
    assert quotes[0]["number"] == quote.number
    assert quotes[0]["status"] == QuoteStatus.SENT

    pdf = cab.get(f"/api/account/quotes/{quote.pk}/pdf/")
    assert pdf.status_code == 200

    docs = cab.get("/api/account/documents/").json()
    assert any(d["kind"] == DocumentKind.QUOTE_PDF for d in docs)

    convs = cab.get("/api/account/conversations/").json()
    assert convs[0]["id"] == conv.pk
    assert convs[0]["channel"] == Channel.WEB

    summary = cab.get("/api/account/summary/").json()
    assert summary["active_leads"] == 0, "завершённая заявка не должна быть активной"
    assert summary["quotes_pending"] == 1
    assert summary["unread_conversations"] == 1

    # ── Шаг 7: изоляция — чужой аккаунт не видит данные ──
    other = APIClient()
    _register_cabinet(other, "stranger@other.test", "Чужой")
    assert other.get(f"/api/account/quotes/{quote.pk}/").status_code == 404
    assert other.get(f"/api/account/quotes/{quote.pk}/pdf/").status_code == 404
    assert other.get(f"/api/account/documents/{doc.pk}/download/").status_code == 404
    assert other.get(f"/api/account/leads/{lead.pk}/").status_code == 404
    assert other.get("/api/account/conversations/").json() == []

    # ── Шаг 8: менеджер видит всю цепочку на карточке клиента в админке ──
    page = admin_client.get(reverse("admin:crm_client_change", args=[client.pk]))
    assert page.status_code == 200
    html = page.content.decode()
    assert quote.number in html, "номер КП не виден на карточке клиента"
    assert "Входящая заявка" in html or "Звонок" in html or msg.subject in html


@pytest.mark.django_db
def test_web_conversation_auto_links_to_client_card() -> None:
    """Диалог с contact_email сам попадает на карточку (создаёт её при нужде)."""
    client = Client.objects.create(email="chatter@corp.test", name="Чат-клиент")

    api = APIClient()
    resp = api.post(
        "/api/support/conversations/",
        {
            "pdn_consent": True,
            "display_name": "Чат-клиент",
            "contact_email": "chatter@corp.test",
            "website": "",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    conv = Conversation.objects.get(pk=resp.json()["id"])
    assert conv.client_id == client.pk, "диалог не привязался к карточке по email"

    # Новый email → карточка создаётся по правилу досье, диалог линкуется.
    api2 = APIClient()
    resp = api2.post(
        "/api/support/conversations/",
        {"pdn_consent": True, "contact_email": "newbie@fresh.test", "website": ""},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    conv2 = Conversation.objects.get(pk=resp.json()["id"])
    new_client = Client.objects.get(email="newbie@fresh.test")
    assert conv2.client_id == new_client.pk


@pytest.mark.django_db
def test_account_link_backfills_orphan_conversations(settings: Any) -> None:
    """Регистрация подтягивает старые диалоги по contact_email на карточку."""
    site = SiteSettings.load()
    site.cabinet_enabled = True
    site.save()

    client = Client.objects.create(email="legacy@corp.test", name="Легаси")
    orphan = Conversation.objects.create(
        channel=Channel.WEB,
        external_user_id="sess-legacy",
        contact_email="legacy@corp.test",
        status=ConversationStatus.OPEN,
        display_name="Легаси",
        client=None,
    )

    cab = APIClient()
    _register_cabinet(cab, "legacy@corp.test", "Легаси")

    orphan.refresh_from_db()
    assert orphan.client_id == client.pk
    # contact_email в виджете вводит посетитель — без ответа менеджера диалог скрыт.
    assert cab.get("/api/account/conversations/").json() == []

    manager = User.objects.create_user("legacy-mgr", password="x", is_staff=True)
    Message.objects.create(
        conversation=orphan,
        direction=MessageDirection.OUTBOUND,
        body="Добрый день!",
        author=manager,
    )
    convs = cab.get("/api/account/conversations/").json()
    assert convs[0]["id"] == orphan.pk


@pytest.mark.django_db
def test_journey_quote_draft_hidden_from_cabinet(settings: Any) -> None:
    """Черновик КП клиенту не виден — показывается только после выдачи."""
    site = SiteSettings.load()
    site.cabinet_enabled = True
    site.save()

    client = Client.objects.create(
        email="buyer@corp.test",
        name="Покупатель",
        phone="79151112233",
    )
    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Покупатель",
        email="buyer@corp.test",
        company="ООО Корп",
        message="Тестовая заявка для черновика КП.",
        client=client,
        status=Lead.LeadStatus.IN_PROGRESS,
    )
    manager = User.objects.create_user(
        username="mgr2",
        email="mgr2@hoocon.ru",
        password="pw12345678",
        is_staff=True,
    )
    draft = Quote.objects.create(
        client=client,
        lead=lead,
        status=QuoteStatus.DRAFT,
        created_by=manager,
    )

    cab = APIClient()
    _register_cabinet(cab, "buyer@corp.test", "Покупатель")
    assert cab.get("/api/account/quotes/").json() == []
    assert cab.get(f"/api/account/quotes/{draft.pk}/").status_code == 404

    summary = cab.get("/api/account/summary/").json()
    assert summary["quotes_pending"] == 0
    assert summary["active_leads"] == 1
