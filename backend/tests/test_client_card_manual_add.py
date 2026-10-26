"""Заявка и заказ с карточки клиента — та же кнопка, что у документа."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client as DjangoClient
from django.urls import reverse

from crm.models import Client
from tests.test_admin_scope_hardening import _admin_change_post


def _staff(username: str, *codenames: str) -> User:
    user = User.objects.create_user(username=username, password="password12", is_staff=True)
    perms = Permission.objects.filter(codename__in=codenames)
    user.user_permissions.set(perms)
    return user


@pytest.mark.django_db
def test_viewer_does_not_get_manual_lead_or_order_rows() -> None:
    """Роль без права добавлять заявку и заказ не видит пустую строку на карточке."""
    viewer = _staff("card-viewer", "view_client", "change_client", "view_lead", "view_order")
    person = Client.objects.create(
        name="Иван",
        email="ivan-card@acme.test",
        company="Акме",
        assignee=viewer,
    )
    page = DjangoClient()
    page.force_login(viewer)
    url = reverse("admin:crm_client_change", args=[person.pk])
    html = page.get(url).content.decode()
    assert "leads-__prefix__-message" not in html
    assert "orders-__prefix__-number" not in html
    assert "quotes-__prefix__-comment" not in html

    posted = _admin_change_post(page, url)

    def forge(prefix: str, fields: dict[str, str]) -> None:
        if f"{prefix}-TOTAL_FORMS" not in posted:
            posted[f"{prefix}-INITIAL_FORMS"] = "0"
            posted[f"{prefix}-MIN_NUM_FORMS"] = "0"
            posted[f"{prefix}-MAX_NUM_FORMS"] = "1000"
            index = 0
        else:
            index = int(posted[f"{prefix}-TOTAL_FORMS"])
        posted[f"{prefix}-TOTAL_FORMS"] = str(index + 1)
        posted[f"{prefix}-{index}-id"] = ""
        for key, value in fields.items():
            posted[f"{prefix}-{index}-{key}"] = value

    forge("leads", {"lead_type": "rfq", "message": "Чужая строка", "status": "new", "assignee": ""})
    forge("orders", {"number": "З-ЧУЖОЙ", "status": "accepted", "comment": "нельзя"})
    forge("quotes", {"comment": "нельзя", "vat_rate": "22.00"})
    saved = page.post(url, posted)
    assert saved.status_code in {200, 302}
    assert person.leads.count() == 0
    assert person.orders.count() == 0
    assert person.quotes.count() == 0


@pytest.mark.django_db
def test_manager_adds_a_call_lead_and_order_on_the_client_card() -> None:
    """Звонок с карточки: заявка берёт имя с карточки, пустой номер заказа ставится сам.

    Письмо «заявка с сайта» не уходит — менеджер уже говорит с клиентом.
    """
    admin = User.objects.create_superuser("card-admin", "card-admin@acme.test", "password12")
    person = Client.objects.create(
        name="Марина",
        email="marina-card@acme.test",
        company="Эпоха",
        phone="+7 900 111-22-33",
    )
    page = DjangoClient()
    page.force_login(admin)
    url = reverse("admin:crm_client_change", args=[person.pk])
    opened = page.get(url)
    assert opened.status_code == 200
    html = opened.content.decode()
    assert "leads-__prefix__-message" in html
    assert "orders-__prefix__-number" in html

    posted = _admin_change_post(page, url)
    lead_index = int(posted["leads-TOTAL_FORMS"])
    posted["leads-TOTAL_FORMS"] = str(lead_index + 1)
    posted[f"leads-{lead_index}-id"] = ""
    posted[f"leads-{lead_index}-lead_type"] = "rfq"
    posted[f"leads-{lead_index}-message"] = "Звонок: два привода SA10"
    posted[f"leads-{lead_index}-status"] = "new"
    posted[f"leads-{lead_index}-assignee"] = ""
    order_index = int(posted["orders-TOTAL_FORMS"])
    posted["orders-TOTAL_FORMS"] = str(order_index + 1)
    posted[f"orders-{order_index}-id"] = ""
    posted[f"orders-{order_index}-number"] = ""
    posted[f"orders-{order_index}-status"] = "accepted"
    posted[f"orders-{order_index}-comment"] = "Сразу в заказ"

    with patch("leads.lifecycle.on_lead_created") as notify:
        saved = page.post(url, posted)
    assert saved.status_code == 302, saved.status_code
    notify.assert_not_called()

    lead = person.leads.get()
    assert lead.name == "Марина"
    assert lead.email == "marina-card@acme.test"
    assert lead.company == "Эпоха"
    assert lead.message == "Звонок: два привода SA10"
    assert lead.contact_verified is True
    assert lead.assignee_id == admin.pk
    order = person.orders.get()
    assert order.number.startswith("З-")
    assert order.comment == "Сразу в заказ"
    assert order.quote_id is None


@pytest.mark.django_db
def test_manager_adds_a_quote_on_the_client_card_and_picks_sku_inside_it() -> None:
    """Товар выбирается в КП, не в заявке и не в заказе. Черновик КП заводится с карточки."""
    admin = User.objects.create_superuser("card-quote-admin", "card-quote-admin@acme.test", "password12")
    person = Client.objects.create(name="Марина", email="marina-quote@acme.test", company="Эпоха")
    page = DjangoClient()
    page.force_login(admin)
    url = reverse("admin:crm_client_change", args=[person.pk])
    assert "quotes-__prefix__-comment" in page.get(url).content.decode()

    posted = _admin_change_post(page, url)
    index = int(posted["quotes-TOTAL_FORMS"])
    posted["quotes-TOTAL_FORMS"] = str(index + 1)
    posted[f"quotes-{index}-id"] = ""
    posted[f"quotes-{index}-comment"] = "Звонок: посчитать SA10"
    posted[f"quotes-{index}-vat_rate"] = "22.00"

    saved = page.post(url, posted)
    assert saved.status_code == 302, saved.status_code
    quote = person.quotes.get()
    assert quote.status == "draft"
    assert quote.comment == "Звонок: посчитать SA10"
    assert quote.vat_rate == 22
    assert quote.number.startswith("КП-")
    assert quote.created_by_id == admin.pk
    quote_page = page.get(reverse("admin:crm_quote_change", args=[quote.pk]))
    assert quote_page.status_code == 200
    body = quote_page.content.decode()
    assert "items-__prefix__-sku" in body
    assert "items-__prefix__-unit_price" in body
