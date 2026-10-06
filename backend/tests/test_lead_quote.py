"""«Создать КП» из карточки заявки: Quote из позиций, дедуп, автозакрытие.

Регресс на воронку «заявка → КП»: заявка закрывается результатом
(статус КП «Выдано» → set_lead_status done), а не «просто done».
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client as DjClient
from django.urls import reverse

from crm.models import Quote, QuoteStatus
from leads.models import Lead, LeadItem

User = get_user_model()


def _staff_with_perms(*, username: str, codenames: tuple[str, ...]) -> Any:
    """Create staff user with given model permissions."""
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def _superuser() -> Any:
    """Admin user without scope limits."""
    return User.objects.create_superuser(
        username="root",
        email="root@example.com",
        password="password12",
    )


def _make_lead(**overrides: Any) -> Lead:
    """Minimal valid RFQ lead."""
    defaults: dict[str, Any] = {
        "lead_type": Lead.LeadType.RFQ,
        "name": "Покупатель",
        "email": "buyer-quote@example.com",
        "company": 'ООО "Ромашка"',
        "message": "x" * 20,
    }
    defaults.update(overrides)
    return Lead.objects.create(**defaults)


@pytest.mark.django_db
def test_create_quote_copies_lead_items_and_links() -> None:
    """КП создаётся из заявки: позиции скопированы, client/lead привязаны."""
    admin = _superuser()
    lead = _make_lead()
    LeadItem.objects.create(lead=lead, sku_code="DA24-NS", quantity=3, sort_order=0)
    LeadItem.objects.create(lead=lead, sku_code="SA10", quantity=1, sort_order=1)
    page = DjClient()
    page.force_login(admin)

    response = page.get(reverse("admin:leads_lead_create_quote", args=[lead.pk]))

    quote = Quote.objects.get(lead=lead)
    assert response.status_code == 302
    assert response.url == reverse("admin:crm_quote_change", args=[quote.pk])
    assert quote.status == QuoteStatus.DRAFT
    assert quote.number == f"КП-{quote.pk}"
    assert quote.client_id == lead.client_id
    assert quote.created_by_id == admin.pk
    items = list(quote.items.order_by("sort_order"))
    assert [(i.sku_code, i.quantity) for i in items] == [
        ("DA24-NS", 3),
        ("SA10", 1),
    ]


@pytest.mark.django_db
def test_create_quote_twice_reuses_open_quote() -> None:
    """Повторный клик → то же открытое КП, дубль не создаётся."""
    admin = _superuser()
    lead = _make_lead()
    page = DjClient()
    page.force_login(admin)
    url = reverse("admin:leads_lead_create_quote", args=[lead.pk])

    page.get(url)
    page.get(url)

    assert Quote.objects.filter(lead=lead).count() == 1


@pytest.mark.django_db
def test_quote_sent_closes_source_lead() -> None:
    """Статус КП «Выдано» → заявка автоматически завершена результатом."""
    admin = _superuser()
    lead = _make_lead(status=Lead.LeadStatus.IN_PROGRESS, assignee=admin)
    quote = Quote.objects.create(client=lead.client, lead=lead, created_by=admin)
    page = DjClient()
    page.force_login(admin)

    response = page.post(
        reverse("admin:crm_quote_change", args=[quote.pk]),
        {
            "status": QuoteStatus.SENT,
            "client": str(quote.client_id),
            "lead": str(lead.pk),
            "created_by": "",
            "comment": "",
            "items-TOTAL_FORMS": "0",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "1000",
        },
    )

    lead.refresh_from_db()
    quote.refresh_from_db()
    assert response.status_code == 302
    assert quote.status == QuoteStatus.SENT
    assert quote.sent_at is not None
    assert lead.status == Lead.LeadStatus.DONE
    assert lead.processed_by_id == admin.pk


@pytest.mark.django_db
def test_create_quote_requires_add_quote_perm() -> None:
    """Без crm.add_quote кнопка недоступна (403)."""
    staff = _staff_with_perms(
        username="no-quote",
        codenames=("view_lead", "change_lead"),
    )
    lead = _make_lead()
    page = DjClient()
    page.force_login(staff)

    response = page.get(reverse("admin:leads_lead_create_quote", args=[lead.pk]))

    assert response.status_code == 403
    assert Quote.objects.count() == 0
