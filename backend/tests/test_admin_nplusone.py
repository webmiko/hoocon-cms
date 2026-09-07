"""Regression tests for Admin changelist N+1 (FK in list_display without eager load)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

User = get_user_model()


def _admin_client(db: object) -> Client:
    user = User.objects.create_superuser(
        username="nplusone-admin",
        email="nplusone-admin@example.com",
        password="x",
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def admin_client(db: object) -> Client:  # type: ignore[misc]
    return _admin_client(db)


@pytest.mark.django_db
def test_sku_admin_list_queries_do_not_scale_with_rows(admin_client: Client) -> None:
    """SKU changelist select_related('product') keeps query count flat."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="N+1", slug="nplusone")
    product = Product.objects.create(name="P", slug="p-np", category=cat)
    SKU.objects.create(
        product=product,
        name="S0",
        slug="s0-np",
        sku_code="S0-NP",
        is_published=True,
    )

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(reverse("admin:catalog_sku_changelist"))
        assert response.status_code == 200
        return len(ctx.captured_queries)

    one = count_queries()

    for index in range(1, 5):
        SKU.objects.create(
            product=product,
            name=f"S{index}",
            slug=f"s{index}-np",
            sku_code=f"S{index}-NP",
            is_published=True,
        )

    assert count_queries() <= one + 1


@pytest.mark.django_db
def test_client_admin_list_queries_do_not_scale_with_rows(admin_client: Client) -> None:
    """Client changelist select_related('assignee') keeps query count flat."""
    from crm.models import Client

    Client.objects.create(name="C0", email="c0-np@example.com")

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(reverse("admin:crm_client_changelist"))
        assert response.status_code == 200
        return len(ctx.captured_queries)

    one = count_queries()

    for index in range(1, 5):
        Client.objects.create(name=f"C{index}", email=f"c{index}-np@example.com")

    assert count_queries() <= one + 1


@pytest.mark.django_db
def test_lead_admin_rfq_thread_badge_query_count_flat(admin_client: Client) -> None:
    """Lead changelist rfq_thread_badge uses annotation, not per-row count."""
    from crm.models import Client
    from leads.models import Lead

    client = Client.objects.create(name="Thread", email="thread@example.com", company="A")
    Lead.objects.create(
        name="Root",
        email="root@example.com",
        company="A",
        lead_type=Lead.LeadType.RFQ,
        status=Lead.LeadStatus.NEW,
        client=client,
        message="",
    )

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = admin_client.get(reverse("admin:leads_lead_changelist"))
        assert response.status_code == 200
        return len(ctx.captured_queries)

    one = count_queries()

    for index in range(1, 5):
        Lead.objects.create(
            name=f"Sibling {index}",
            email=f"sib{index}@example.com",
            company="A",
            lead_type=Lead.LeadType.RFQ,
            status=Lead.LeadStatus.NEW,
            client=client,
            message="",
        )

    assert count_queries() <= one + 1
