"""Client «заявка принята в работу» email + manager reply-button tests.

Покрывает:
- render_lead_client_confirmation — тема/номер/дата/менеджер в теле письма;
- send_lead_client_confirmation — to=lead.email, Reply-To = менеджер или sales;
- POST /api/leads/ ставит клиентскую Celery-таску через on_commit;
- письмо менеджеру содержит кнопку «Ответить клиенту» (Yandex web compose).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings

from leads.models import Lead, LeadItem
from leads.services import (
    render_lead_client_confirmation,
    render_lead_notification,
    resolve_lead_reply_to,
)
from leads.tasks import send_lead_client_confirmation

User = get_user_model()


def _make_manager(*, username: str = "mgr-confirm", email: str = "mgr@hoocon.ru") -> User:
    return User.objects.create_user(
        username=username,
        email=email,
        password="password12",
        is_staff=True,
        first_name="Людмила",
    )


def _make_lead(**overrides: object) -> Lead:
    defaults: dict[str, object] = {
        "name": "Иван Петров",
        "email": "ivan@example.com",
        "company": "ООО Ромашка",
        "message": "Нужен КП на 10 приводов HVA-5NM для объекта.",
        "lead_type": Lead.LeadType.RFQ,
    }
    defaults.update(overrides)
    return Lead.objects.create(**defaults)


# ── Render ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_render_client_confirmation_contains_details() -> None:
    """Тема/тело: номер заявки, имя, тип, дата, позиции, телефон и сайт."""
    lead = _make_lead()
    LeadItem.objects.create(lead=lead, sku_code="HVA-5NM", quantity=10, sort_order=0)
    subject, text_body, html_body = render_lead_client_confirmation(lead)
    assert subject == f"Мы получили вашу заявку №{lead.pk}"
    for body in (text_body, html_body):
        assert "Иван Петров" in body
        assert f"№{lead.pk}" in body
        assert "Запрос КП" in body
        assert "HVA-5NM" in body
        assert "8 800 350-58-98" in body
        assert 'ООО "ХОГОН"' in body  # |safe — кавычки не в &quot;
        assert "2 рабочих часов" in body


@pytest.mark.django_db
def test_render_client_confirmation_names_assignee() -> None:
    """С назначенным менеджером подпись — его имя и личная почта."""
    lead = _make_lead(assignee=_make_manager())
    subject, text_body, html_body = render_lead_client_confirmation(lead)
    assert "Людмила" in text_body
    assert "mgr@hoocon.ru" in text_body
    assert "Людмила" in html_body
    assert "mgr@hoocon.ru" in html_body


@pytest.mark.django_db
def test_render_client_confirmation_uses_manager_contacts() -> None:
    """Подпись берёт телефон/почту менеджера из _MANAGER_CONTACTS."""
    lead = _make_lead(assignee=_make_manager(email="assistant@hoocon.ru"))
    _, text_body, html_body = render_lead_client_confirmation(lead)
    assert "+7(995)780-70-18" in text_body
    assert "assistant@hoocon.ru" in text_body
    assert "+7(995)780-70-18" in html_body
    assert "mailto:assistant@hoocon.ru" in html_body
    # Общий телефон сайта в подписи не показывается, когда есть личный.
    assert "8 800 350-58-98" not in text_body


@pytest.mark.django_db
def test_render_client_confirmation_without_assignee_uses_team() -> None:
    """Без назначенного менеджера подпись — «Команда продаж» + общий телефон."""
    lead = _make_lead()
    _, text_body, html_body = render_lead_client_confirmation(lead)
    assert "Команда продаж" in text_body
    assert "Команда продаж" in html_body
    assert "8 800 350-58-98" in text_body


# ── Reply-To resolution ──────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_reply_to_prefers_assignee_email() -> None:
    """Reply-To — почта активного менеджера, а не общий ящик."""
    lead = _make_lead(assignee=_make_manager(email="ivan@hoocon.ru"))
    assert resolve_lead_reply_to(lead) == "ivan@hoocon.ru"


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru, backup@hoocon.ru")
def test_reply_to_falls_back_to_sales_list() -> None:
    """Без менеджера Reply-To — первый адрес из LEAD_NOTIFY_EMAIL."""
    lead = _make_lead()
    assert resolve_lead_reply_to(lead) == "sales@hoocon.ru"


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="")
def test_reply_to_empty_when_nothing_configured() -> None:
    """Ни менеджера, ни LEAD_NOTIFY_EMAIL → Reply-To не ставится."""
    lead = _make_lead()
    assert resolve_lead_reply_to(lead) == ""


# ── Celery task ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_send_client_confirmation_goes_to_client() -> None:
    """Письмо уходит клиенту (to=lead.email) с Reply-To на менеджера."""
    lead = _make_lead(assignee=_make_manager(email="ivan@hoocon.ru"))
    mail.outbox.clear()
    send_lead_client_confirmation.apply(args=[lead.pk]).get()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["ivan@example.com"]
    assert msg.reply_to == ["ivan@hoocon.ru"]
    assert f"№{lead.pk}" in msg.subject
    assert msg.alternatives and msg.alternatives[0][1] == "text/html"


@pytest.mark.django_db
def test_send_client_confirmation_skips_missing_lead() -> None:
    """Unknown lead_id — no-op (no mail, no crash)."""
    mail.outbox.clear()
    send_lead_client_confirmation.apply(args=[9_999_999]).get()
    assert mail.outbox == []


# ── View wiring ──────────────────────────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_post_lead_schedules_client_confirmation(client) -> None:
    """POST /api/leads/ ставит send_lead_client_confirmation через on_commit."""
    from unittest.mock import patch

    payload = {
        "name": "Anna",
        "email": "anna@example.com",
        "company": "ООО ВентСервис",
        "message": "Помогите подобрать привод для вентиляции.",
    }
    with patch("leads.views.send_lead_client_confirmation") as mock_task:
        response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 201
    lead = Lead.objects.first()
    assert lead is not None
    mock_task.delay.assert_called_once_with(lead.pk)


# ── Manager email reply button ───────────────────────────────────────


@pytest.mark.django_db
def test_manager_email_has_reply_button() -> None:
    """Письмо менеджеру: кнопка «Ответить клиенту» → Yandex web compose."""
    lead = _make_lead()
    _, text_body, html_body = render_lead_notification(lead)
    assert "mail.yandex.ru/compose" in html_body
    assert "Ответить клиенту" in html_body
    assert "ivan@example.com" in html_body  # адрес клиента внутри compose URL
    assert "mail.yandex.ru/compose" in text_body
