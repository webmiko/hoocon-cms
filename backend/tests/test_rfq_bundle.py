"""RFQ multi-SKU items + soft-bundle by company+name."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from catalog.models import SKU, Category, Product
from leads.models import Lead, LeadItem
from leads.rfq_bundle import (
    attach_rfq_bundle,
    build_rfq_bundle_key,
    mark_rfq_bundle_done,
    rfq_bundle_queryset,
)


def _sku(code: str, *, slug: str | None = None) -> SKU:
    cat, _ = Category.objects.get_or_create(
        slug="test-rfq-cat",
        defaults={"name": "Test"},
    )
    product, _ = Product.objects.get_or_create(
        slug=f"prod-{code.lower()}",
        defaults={"name": code, "category": cat},
    )
    sku, _ = SKU.objects.update_or_create(
        sku_code=code,
        defaults={
            "slug": slug or code.lower().replace("_", "-"),
            "name": code,
            "product": product,
            "is_published": True,
        },
    )
    return sku


@pytest.mark.django_db
def test_build_rfq_bundle_key_normalizes() -> None:
    """Company/name collapse spaces and casefold."""
    a = build_rfq_bundle_key(company="ООО  Ромашка", name="Иван")
    b = build_rfq_bundle_key(company="ооо ромашка", name="иван")
    assert a == b
    assert a.startswith("ооо ромашка|")


@pytest.mark.django_db
def test_post_rfq_requires_company(client) -> None:
    """RFQ without company → 400."""
    response = client.post(
        "/api/leads/",
        data={
            "lead_type": "rfq",
            "name": "Иван",
            "email": "a@example.com",
            "message": "Нужен КП на приводы для объекта.",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "company" in response.json()


@pytest.mark.django_db
def test_post_rfq_items_creates_lead_items(client) -> None:
    """items[] create LeadItem rows and legacy sku summary."""
    s1 = _sku("HVA-5NM", slug="hva-5nm")
    s2 = _sku("HVA-10NM", slug="hva-10nm")
    response = client.post(
        "/api/leads/",
        data={
            "lead_type": "rfq",
            "name": "Иван",
            "email": "a@example.com",
            "company": "ООО Ромашка",
            "message": "Прошу подготовить КП по списку артикулов.",
            "items": [
                {"sku": s1.slug, "quantity": 2},
                {"sku": s2.slug, "quantity": 5},
            ],
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    lead = Lead.objects.get(pk=response.json()["id"])
    assert lead.sku_id == s1.pk
    assert lead.quantity == 2
    codes = list(lead.items.order_by("sort_order").values_list("sku_code", "quantity"))
    assert codes == [("HVA-5NM", 2), ("HVA-10NM", 5)]
    assert lead.rfq_bundle_key == build_rfq_bundle_key(
        company="ООО Ромашка",
        name="Иван",
    )
    assert lead.rfq_bundle_root_id is None


@pytest.mark.django_db
def test_post_legacy_sku_creates_one_item(client) -> None:
    """Legacy sku field still creates a single LeadItem."""
    s1 = _sku("DA24-5", slug="da24-5")
    response = client.post(
        "/api/leads/",
        data={
            "lead_type": "rfq",
            "name": "Пётр",
            "email": "b@example.com",
            "company": "АО Тест",
            "message": "Нужен КП на один привод для щита.",
            "sku": s1.slug,
            "quantity": 3,
        },
        content_type="application/json",
    )
    assert response.status_code == 201
    lead = Lead.objects.get(pk=response.json()["id"])
    assert LeadItem.objects.filter(lead=lead).count() == 1
    item = lead.items.get()
    assert item.sku_id == s1.pk
    assert item.quantity == 3


@pytest.mark.django_db
def test_rfq_bundle_attaches_second_lead() -> None:
    """Second open RFQ with same company+name points at the first root."""
    first = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Первая заявка на КП для объекта.",
    )
    attach_rfq_bundle(first)
    first.refresh_from_db()
    assert first.rfq_bundle_root_id is None

    second = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="иван",
        email="a2@example.com",
        company="ооо  ромашка",
        message="Вторая заявка на дополнительные артикулы.",
    )
    attach_rfq_bundle(second)
    second.refresh_from_db()
    assert second.rfq_bundle_root_id == first.pk
    assert rfq_bundle_queryset(second).count() == 2


@pytest.mark.django_db
def test_rfq_bundle_different_company_new_thread() -> None:
    """Different company → new root."""
    first = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="Компания А",
        message="КП для компании А на объекте.",
    )
    attach_rfq_bundle(first)
    other = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="Компания Б",
        message="КП для компании Б на объекте.",
    )
    attach_rfq_bundle(other)
    other.refresh_from_db()
    assert other.rfq_bundle_root_id is None
    assert other.rfq_bundle_key != first.rfq_bundle_key


@pytest.mark.django_db
def test_rfq_bundle_done_root_starts_new_thread() -> None:
    """Done root does not absorb a new open RFQ."""
    first = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Старая завершённая заявка на КП.",
        status=Lead.LeadStatus.DONE,
        processed_at=timezone.now() - timedelta(days=1),
    )
    attach_rfq_bundle(first)
    first.refresh_from_db()

    second = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Новая заявка после закрытой нити.",
    )
    attach_rfq_bundle(second)
    second.refresh_from_db()
    assert second.rfq_bundle_root_id is None


@pytest.mark.django_db
def test_mark_rfq_bundle_done(django_user_model) -> None:
    """Action helper closes all open siblings."""
    manager = django_user_model.objects.create_user(
        username="mgr",
        email="mgr@example.com",
        is_staff=True,
    )
    a = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Корень нити КП для теста.",
    )
    attach_rfq_bundle(a)
    b = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Дочерняя заявка нити КП.",
    )
    attach_rfq_bundle(b)
    n = mark_rfq_bundle_done(b, actor=manager)
    assert n == 2
    assert Lead.objects.filter(status=Lead.LeadStatus.DONE).count() == 2


@pytest.mark.django_db
def test_consultation_without_company_ok(client) -> None:
    """Non-RFQ leads do not require company."""
    response = client.post(
        "/api/leads/",
        data={
            "lead_type": "consultation",
            "name": "Анна",
            "email": "anna@example.com",
            "message": "Помогите подобрать привод для вентиляции.",
        },
        content_type="application/json",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_render_notification_continuation_and_items() -> None:
    """Manager email marks continuation and lists LeadItem rows."""
    from leads.models import LeadItem
    from leads.services import render_lead_notification

    root = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Корень нити для письма менеджеру.",
    )
    attach_rfq_bundle(root)
    child = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Продолжение с дополнительными позициями.",
    )
    attach_rfq_bundle(child)
    LeadItem.objects.create(
        lead=child,
        sku_code="HVA-5NM",
        quantity=2,
        sort_order=0,
    )
    LeadItem.objects.create(
        lead=child,
        sku_code="HVA-10NM",
        quantity=1,
        sort_order=1,
    )
    subject, text_body, html_body = render_lead_notification(child)
    assert "Продолжение КП" in subject
    assert f"#{root.pk}" in subject
    assert "Продолжение КП" in text_body
    assert "HVA-5NM" in text_body
    assert "HVA-10NM" in text_body
    assert "HVA-5NM" in html_body
