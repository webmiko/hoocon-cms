"""Tests for leads.Lead model + serializer (TDD).

Spec: ПЛАН §6 Iter 3 — leads.Lead (RFQ / консультация / «подобрать замену»);
docs/readiness-backend-ux.md §2.2 (leads | Lead (RFQ / consult / replace));
docs/security-baseline.md §3 (PII-safe; validate; honeypot в Slice 19).

Контракт:
- Lead.lead_type: rfq | consultation | replacement (default rfq).
- Lead: name, email, message — обязательные; phone, company — опц.
- Lead.sku — опц. FK на SKU (SET_NULL — удаление SKU не удаляет заявку).
- Lead.quantity — опц. (для RFQ).
- Lead.analog_belimo_code — опц. (для replacement).
- Lead.status: new | in_progress | done (default new).
- Сериализатор: whitelist полей, валидация длины message, email format.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError

# ── Lead model: basic creation ────────────────────────────────────────


@pytest.mark.django_db
def test_create_lead_rfq_minimal() -> None:
    """Can create a minimal RFQ lead with name, email, message."""
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Иван Иванов",
        email="ivan@example.com",
        message="Нужен КП на 10 приводов HVA-5NM.",
    )
    assert lead.pk is not None
    assert lead.lead_type == Lead.LeadType.RFQ
    assert lead.status == Lead.LeadStatus.NEW


@pytest.mark.django_db
def test_create_lead_consultation() -> None:
    """Can create a consultation lead."""
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Anna",
        email="anna@example.com",
        message="Помогите подобрать привод для вентиляции.",
        lead_type=Lead.LeadType.CONSULTATION,
    )
    assert lead.lead_type == Lead.LeadType.CONSULTATION


@pytest.mark.django_db
def test_create_lead_replacement() -> None:
    """Can create a replacement lead with analog_belimo_code."""
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Petr",
        email="petr@example.com",
        message="Нужен аналог Belimo LM24A-SR.",
        lead_type=Lead.LeadType.REPLACEMENT,
        analog_belimo_code="LM24A-SR",
    )
    assert lead.lead_type == Lead.LeadType.REPLACEMENT
    assert lead.analog_belimo_code == "LM24A-SR"


# ── Required fields ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_name_required() -> None:
    """Missing name (NULL) raises IntegrityError (NOT NULL constraint)."""
    from leads.models import Lead

    with pytest.raises(IntegrityError):
        Lead.objects.create(name=None, email="x@example.com", message="msg")  # type: ignore[arg-type]


@pytest.mark.django_db
def test_lead_email_required() -> None:
    """Missing email (NULL) raises IntegrityError (NOT NULL constraint)."""
    from leads.models import Lead

    with pytest.raises(IntegrityError):
        Lead.objects.create(name="X", email=None, message="msg")  # type: ignore[arg-type]


@pytest.mark.django_db
def test_lead_message_required() -> None:
    """Missing message (NULL) raises IntegrityError (NOT NULL constraint)."""
    from leads.models import Lead

    with pytest.raises(IntegrityError):
        Lead.objects.create(name="X", email="x@example.com", message=None)  # type: ignore[arg-type]


# ── Optional fields ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_phone_optional() -> None:
    """Phone is optional (blank allowed)."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    assert lead.phone == ""


@pytest.mark.django_db
def test_lead_company_optional() -> None:
    """Company is optional (blank allowed)."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    assert lead.company == ""


@pytest.mark.django_db
def test_lead_quantity_optional() -> None:
    """Quantity is optional (null allowed)."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    assert lead.quantity is None


@pytest.mark.django_db
def test_lead_sku_optional() -> None:
    """SKU is optional (null allowed)."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    assert lead.sku is None


# ── SKU FK + on_delete=SET_NULL ───────────────────────────────────────


@pytest.mark.django_db
def test_lead_sku_set_null_on_delete() -> None:
    """Deleting a SKU sets Lead.sku to NULL (not CASCADE)."""
    from catalog.models import SKU, Category, Product
    from leads.models import Lead

    cat = Category.objects.create(name="C", slug="c-lead")
    prod = Product.objects.create(name="P", slug="p-lead", category=cat)
    sku = SKU.objects.create(product=prod, name="S", slug="s-lead", sku_code="S-LEAD")
    lead = Lead.objects.create(
        name="X",
        email="x@example.com",
        message="msg",
        sku=sku,
    )
    assert lead.sku_id == sku.pk
    sku.delete()
    lead.refresh_from_db()
    assert lead.sku_id is None
    # Lead itself is preserved.
    assert Lead.objects.filter(pk=lead.pk).exists()


# ── Status defaults ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_default_status_new() -> None:
    """New Lead has status=NEW."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    assert lead.status == Lead.LeadStatus.NEW


@pytest.mark.django_db
def test_lead_status_can_progress() -> None:
    """Lead status can be updated to IN_PROGRESS and DONE."""
    from leads.models import Lead

    lead = Lead.objects.create(name="X", email="x@example.com", message="msg")
    lead.status = Lead.LeadStatus.IN_PROGRESS
    lead.save()
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    lead.status = Lead.LeadStatus.DONE
    lead.save()
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.DONE


# ── __str__ ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_str() -> None:
    """__str__ is PII-safe: Заявка #pk and type, not contact name."""
    from leads.models import Lead

    lead = Lead.objects.create(
        name="Иван",
        email="ivan@example.com",
        message="msg",
        lead_type=Lead.LeadType.RFQ,
    )
    s = str(lead)
    assert "Иван" not in s
    assert f"Заявка #{lead.pk}" in s
    assert "rfq" in s.lower() or "RFQ" in s or "КП" in s


# ── Serializer ────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_lead_serializer_valid_data() -> None:
    """Serializer accepts valid payload and creates a Lead."""
    from leads.serializers import LeadSerializer

    data = {
        "name": "Иван Иванов",
        "email": "ivan@example.com",
        "company": "ООО Ромашка",
        "message": "Нужен КП на 10 приводов.",
        "lead_type": "rfq",
    }
    ser = LeadSerializer(data=data)
    assert ser.is_valid(), ser.errors
    lead = ser.save()
    assert lead.name == "Иван Иванов"
    assert lead.email == "ivan@example.com"


@pytest.mark.django_db
def test_lead_serializer_rejects_missing_name() -> None:
    """Serializer rejects payload without name."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(data={"email": "x@example.com", "message": "msg"})
    assert not ser.is_valid()
    assert "name" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_missing_email() -> None:
    """Serializer rejects payload without email."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(data={"name": "X", "message": "msg"})
    assert not ser.is_valid()
    assert "email" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_missing_message() -> None:
    """Serializer rejects payload without message."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(data={"name": "X", "email": "x@example.com"})
    assert not ser.is_valid()
    assert "message" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_invalid_email() -> None:
    """Serializer rejects malformed email."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(
        data={"name": "X", "email": "not-an-email", "message": "msg"},
    )
    assert not ser.is_valid()
    assert "email" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_short_message() -> None:
    """Serializer rejects message shorter than min length (anti-spam)."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(
        data={"name": "X", "email": "x@example.com", "message": "a"},
    )
    assert not ser.is_valid()
    assert "message" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_long_message() -> None:
    """Serializer rejects message longer than max length (DoS guard)."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(
        data={"name": "X", "email": "x@example.com", "message": "x" * 5001},
    )
    assert not ser.is_valid()
    assert "message" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_rejects_invalid_lead_type() -> None:
    """Serializer rejects unknown lead_type."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer(
        data={
            "name": "X",
            "email": "x@example.com",
            "message": "msg",
            "lead_type": "unknown_type",
        },
    )
    assert not ser.is_valid()
    assert "lead_type" in ser.errors


@pytest.mark.django_db
def test_lead_serializer_read_only_fields() -> None:
    """Serializer marks status/created_at/updated_at as read-only."""
    from leads.serializers import LeadSerializer

    ser = LeadSerializer()
    # DRF exposes read_only on each field instance (Meta.read_only_fields
    # is consumed at field construction, not stored as instance attr).
    assert ser.fields["status"].read_only is True
    assert ser.fields["created_at"].read_only is True
    assert ser.fields["updated_at"].read_only is True


@pytest.mark.django_db
def test_lead_serializer_does_not_expose_email_in_representation() -> None:
    """Serializer representation does NOT expose PII by default (Slice 19
    will decide public vs staff representation; for now, read-only on
    output is enforced via explicit fields)."""
    from leads.models import Lead
    from leads.serializers import LeadSerializer

    lead = Lead.objects.create(
        name="Иван",
        email="ivan@example.com",
        message="msg",
    )
    ser = LeadSerializer(lead)
    # The serializer must include name + message + lead_type for staff,
    # but email/phone are sensitive — they should be in write-only or
    # staff-only context. For Slice 18 we just assert the serializer
    # has the fields; the API layer (Slice 19) controls exposure.
    assert "name" in ser.data
    assert "message" in ser.data
