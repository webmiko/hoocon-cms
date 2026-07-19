"""Tests for Lead API: POST /api/leads/ + Celery email + honeypot + throttle (TDD).

Spec: ПЛАН §6 Iter 3 — Lead API + Celery email + honeypot + throttle;
docs/security-baseline.md §3 (PII не в логах; honeypot silent drop; 429 на throttle).

Контракт:
- POST /api/leads/ с валидными данными → 201, Lead создан, email отправлен.
- POST без обязательных полей → 400.
- POST с заполненным honeypot → 201 (silent drop), Lead НЕ создан, email НЕ отправлен.
- POST > 10/час с одного IP → 429 (throttle).
- PII (email/phone) не возвращается в ответе API (write-only).
- PII не попадает в логи Celery-таски.
"""

from __future__ import annotations

import logging

import pytest
from django.core import mail
from django.test import override_settings

# ── POST /api/leads/ — happy path ─────────────────────────────────────


@pytest.mark.django_db
def test_post_lead_creates_lead_and_returns_201(client) -> None:
    """Valid POST creates a Lead and returns 201."""
    payload = {
        "lead_type": "rfq",
        "name": "Иван Иванов",
        "email": "ivan@example.com",
        "phone": "+7-999-123-45-67",
        "company": "ООО Ромашка",
        "message": "Нужен КП на 10 приводов HVA-5NM для объекта.",
    }
    response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 201
    from leads.models import Lead

    assert Lead.objects.count() == 1
    lead = Lead.objects.first()
    assert lead is not None
    assert lead.name == "Иван Иванов"
    assert lead.email == "ivan@example.com"


@pytest.mark.django_db(transaction=True)
def test_post_lead_sends_notification_email_on_commit(client) -> None:
    """Creating a Lead schedules send_lead_notification via transaction.on_commit.

    Patches `send_lead_notification.delay` to verify the view schedules the
    Celery task after the DB commit (not before — avoids running if the
    transaction rolls back). Uses `transaction=True` so on_commit fires.
    """
    from unittest.mock import patch

    payload = {
        "name": "Anna",
        "email": "anna@example.com",
        "message": "Помогите подобрать привод для вентиляции.",
    }
    with patch("leads.views.send_lead_notification") as mock_task:
        response = client.post(
            "/api/leads/",
            data=payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        # transaction.on_commit fires when the transaction commits (end of test,
        # since transaction=True). The mock's delay should be called with lead_id.
    from leads.models import Lead

    lead = Lead.objects.first()
    assert lead is not None
    mock_task.delay.assert_called_once_with(lead.pk)


@pytest.mark.django_db
def test_lead_notification_task_sends_email() -> None:
    """The Celery task send_lead_notification sends an email to LEAD_NOTIFY_EMAIL."""
    from leads.models import Lead
    from leads.tasks import send_lead_notification

    lead = Lead.objects.create(
        name="Petr",
        email="petr@example.com",
        phone="+7-999-000-00-01",
        message="Нужен аналог Belimo LM24A-SR.",
        lead_type=Lead.LeadType.REPLACEMENT,
        analog_belimo_code="LM24A-SR",
    )
    mail.outbox.clear()
    with override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru"):
        send_lead_notification.apply(args=[lead.pk]).get()
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == ["sales@hoocon.ru"]
    # Subject mentions lead type.
    assert "заявк" in msg.subject.lower() or "replacement" in msg.subject.lower() or "замена" in msg.subject.lower()
    # Body contains the lead info for the manager.
    assert "Petr" in msg.body
    assert "petr@example.com" in msg.body
    assert "LM24A-SR" in msg.body


# ── Validation: missing fields → 400 ─────────────────────────────────


@pytest.mark.django_db
def test_post_lead_missing_name_returns_400(client) -> None:
    """POST without name returns 400."""
    response = client.post(
        "/api/leads/",
        data={"email": "x@example.com", "message": "a" * 20},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "name" in response.json()


@pytest.mark.django_db
def test_post_lead_missing_email_returns_400(client) -> None:
    """POST without email returns 400."""
    response = client.post(
        "/api/leads/",
        data={"name": "X", "message": "a" * 20},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.django_db
def test_post_lead_missing_message_returns_400(client) -> None:
    """POST without message returns 400."""
    response = client.post(
        "/api/leads/",
        data={"name": "X", "email": "x@example.com"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "message" in response.json()


@pytest.mark.django_db
def test_post_lead_invalid_email_returns_400(client) -> None:
    """POST with malformed email returns 400."""
    response = client.post(
        "/api/leads/",
        data={"name": "X", "email": "not-an-email", "message": "a" * 20},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "email" in response.json()


# ── Honeypot: silent drop ─────────────────────────────────────────────


@pytest.mark.django_db
def test_post_lead_honeypot_filled_silent_drop(client) -> None:
    """Honeypot field filled → 201 returned but NO Lead created (silent drop)."""
    payload = {
        "name": "Bot",
        "email": "bot@spam.com",
        "message": "spam message that is long enough",
        "website": "http://spam-site.example",  # honeypot — bots fill hidden fields
    }
    response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 201  # pretend success to confuse bot
    from leads.models import Lead

    assert Lead.objects.count() == 0  # but no lead actually created


@pytest.mark.django_db
def test_post_lead_honeypot_empty_creates_lead(client) -> None:
    """Honeypot field empty → normal creation (lead created)."""
    payload = {
        "name": "Real User",
        "email": "real@example.com",
        "message": "a real message that is long enough",
        "website": "",  # honeypot empty
    }
    response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 201
    from leads.models import Lead

    assert Lead.objects.count() == 1


# ── PII-safe response ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_post_lead_response_does_not_expose_email_or_phone(client) -> None:
    """API response does NOT include email/phone (PII write-only)."""
    payload = {
        "name": "X",
        "email": "secret@example.com",
        "phone": "+7-999-000-00-00",
        "message": "a message that is long enough",
    }
    response = client.post("/api/leads/", data=payload, content_type="application/json")
    assert response.status_code == 201
    body = response.json()
    assert "email" not in body
    assert "phone" not in body
    # Non-PII fields are present for confirmation.
    assert body.get("name") == "X"
    assert body.get("status") == "new"


# ── Throttle: > 10/hour → 429 ─────────────────────────────────────────


@pytest.mark.django_db
def test_post_lead_throttle_after_limit(client) -> None:
    """> 10 POST /api/leads/ per hour from same IP → 429."""
    payload = {
        "name": "X",
        "email": "x@example.com",
        "message": "a message that is long enough",
    }
    # First 10 should succeed (or 400 if validation fails, but throttle counts).
    statuses = []
    for i in range(12):
        data = {**payload, "email": f"x{i}@example.com"}
        r = client.post("/api/leads/", data=data, content_type="application/json")
        statuses.append(r.status_code)
    # At least one of the later requests must be 429.
    assert 429 in statuses, f"Expected 429 in throttle test; got {statuses}"


# ── PII not in logs ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_task_does_not_log_pii(caplog) -> None:
    """Celery task logs do NOT contain email or phone (PII-safe logging)."""
    from leads.models import Lead
    from leads.tasks import send_lead_notification

    lead = Lead.objects.create(
        name="Test User",
        email="pii-email@example.com",
        phone="+7-999-PII-PHONE",
        message="a message that is long enough",
    )
    caplog.set_level(logging.INFO, logger="hoocon")
    with override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru"):
        send_lead_notification.apply(args=[lead.pk]).get()
    # Logs must not contain the raw email or phone.
    log_text = caplog.text
    assert "pii-email@example.com" not in log_text
    assert "+7-999-PII-PHONE" not in log_text
    # But the task should have logged something (lead_id, type).
    assert "lead" in log_text.lower() or "заявка" in log_text.lower()


# ── Read-only: GET not allowed ────────────────────────────────────────


@pytest.mark.django_db
def test_get_leads_not_allowed(client) -> None:
    """GET /api/leads/ is not allowed (write-only endpoint)."""
    response = client.get("/api/leads/")
    assert response.status_code == 405
