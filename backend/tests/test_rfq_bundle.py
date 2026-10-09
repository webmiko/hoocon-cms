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
def test_post_lead_ignores_invalid_basic_auth(client) -> None:
    """Invalid Basic credentials must not turn a public lead POST into 401."""
    response = client.post(
        "/api/leads/",
        data={
            "pdn_consent": True,
            "lead_type": "consultation",
            "name": "Иван",
            "company": "ООО Тест",
            "email": "a@example.com",
            "message": "Нужен подбор привода под задвижку DN50.",
        },
        content_type="application/json",
        HTTP_AUTHORIZATION="Basic invalid",
    )
    assert response.status_code == 201


@pytest.mark.django_db
def test_post_rfq_requires_company(client) -> None:
    """RFQ without company → 400."""
    response = client.post(
        "/api/leads/",
        data={
            "pdn_consent": True,
            "lead_type": "rfq",
            "name": "Иван",
            "email": "a@example.com",
            "message": "Нужен КП на приводы для объекта.",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.json()
    assert "company" in body
    assert "компанию" in str(body["company"]).lower()


@pytest.mark.django_db
def test_post_consultation_requires_company(client) -> None:
    """Consultation without company → 400 (same rule as RFQ)."""
    response = client.post(
        "/api/leads/",
        data={
            "pdn_consent": True,
            "lead_type": "consultation",
            "name": "Иван",
            "email": "a@example.com",
            "message": "Нужен подбор привода под задвижку DN50.",
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
            "pdn_consent": True,
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
            "pdn_consent": True,
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
def test_lead_admin_bundle_size_counts_root_and_siblings(django_user_model) -> None:
    """Changelist annotation must not split root (NULL fk) from siblings."""
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from leads.admin import LeadAdmin

    admin_user = django_user_model.objects.create_superuser(
        username="bundle-ann",
        email="bundle-ann@example.com",
        password="x",
    )
    a = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Корень нити КП для теста аннотации.",
    )
    attach_rfq_bundle(a)
    b = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="a@example.com",
        company="ООО Ромашка",
        message="Дочерняя заявка нити КП для аннотации.",
    )
    attach_rfq_bundle(b)
    request = RequestFactory().get("/admin/leads/lead/")
    request.user = admin_user
    request.resolver_match = type("M", (), {"url_name": "leads_lead_changelist"})()
    qs = LeadAdmin(Lead, site).get_queryset(request)
    sizes = {row.pk: row._bundle_size for row in qs.filter(pk__in=[a.pk, b.pk])}
    assert sizes[a.pk] == 2
    assert sizes[b.pk] == 2


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


@pytest.mark.django_db
def test_rfq_bundle_root_lookup_waits_for_concurrent_lead() -> None:
    """M21: поиск корня нити держит advisory-lock по ключу.

    Без блокировки две параллельные RFQ с одной компанией+именем обе
    становились корнями. Вторая сессия держит lock → attach ждёт.
    """
    from django.db import OperationalError, connections, transaction

    lead = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email="lock@example.com",
        company="ООО Замок",
        message="Заявка на КП, проверка блокировки нити.",
    )
    key = build_rfq_bundle_key(company=lead.company, name=lead.name)
    other = connections.create_connection("default")
    try:
        with other.cursor() as cursor:
            cursor.execute("BEGIN")
            cursor.execute("SELECT pg_advisory_xact_lock(7301, hashtext(%s))", [key])
        with pytest.raises(OperationalError, match="lock timeout"), transaction.atomic():
            with transaction.get_connection().cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '200ms'")
            attach_rfq_bundle(lead)
    finally:
        with other.cursor() as cursor:
            cursor.execute("ROLLBACK")
        other.close()


@pytest.mark.django_db
def test_lead_post_survives_db_error_in_crm_link_signal(client) -> None:
    """M22: ошибка БД в «best-effort» сигнале не роняет заявку в 500.

    Сигнал ловил DatabaseError без savepoint: транзакция заявки уже
    сломана, LeadItem/bundle падали TransactionManagementError.
    """
    from unittest.mock import patch

    from django.db import connection

    def _broken_link(lead: Lead) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM crm_table_that_does_not_exist")

    sku = _sku("HVA-20NM", slug="hva-20nm")
    with (
        patch("crm.services.link_lead_to_client", _broken_link),
        patch("leads.lifecycle.send_lead_notification"),
        patch("leads.lifecycle.send_lead_client_confirmation"),
    ):
        response = client.post(
            "/api/leads/",
            data={
                "pdn_consent": True,
                "lead_type": "rfq",
                "name": "Иван",
                "email": "sig@example.com",
                "company": "ООО Сигнал",
                "message": "Прошу КП, проверка сигнала связи с CRM.",
                "items": [{"sku": sku.slug, "quantity": 1}],
            },
            content_type="application/json",
        )

    assert response.status_code == 201
    lead = Lead.objects.get(pk=response.json()["id"])
    assert lead.items.count() == 1
    assert lead.client_id is None


def _thread(size: int) -> Lead:
    root = Lead.objects.create(
        lead_type=Lead.LeadType.RFQ,
        name="Иван",
        email=f"thread{size}@example.com",
        company=f"ООО Нить {size}",
        message="Корень нити для проверки запросов.",
        rfq_bundle_key=f"thread-{size}",
    )
    for idx in range(size):
        sibling = Lead.objects.create(
            lead_type=Lead.LeadType.RFQ,
            name="Иван",
            email=f"thread{size}@example.com",
            company=f"ООО Нить {size}",
            message="Сосед по нити для проверки запросов.",
            rfq_bundle_key=f"thread-{size}",
            rfq_bundle_root=root,
        )
        sibling.items.create(sku_code=f"SKU-{idx}", quantity=1)
    return root


@pytest.mark.django_db
def test_rfq_thread_links_query_count_flat() -> None:
    """Ссылки нити делали запрос позиций на каждую заявку (N+1)."""
    from django.contrib import admin
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from leads.admin import LeadAdmin

    model_admin = LeadAdmin(Lead, admin.site)
    counts = []
    for size in (2, 6):
        root = _thread(size)
        with CaptureQueriesContext(connection) as ctx:
            html = model_admin.rfq_thread_links(root)
        counts.append(len(ctx.captured_queries))
        assert "SKU-0" in html
    assert counts[0] == counts[1]
