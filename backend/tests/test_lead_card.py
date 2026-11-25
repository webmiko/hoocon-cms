"""Lead page panel: next step by real state, the client's words and history."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.lead_card import build_lead_card
from crm.models import Activity, ActivityType, Quote, QuoteStatus
from leads.models import Lead, LeadItem

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _lead(name: str = "Мария", **extra: Any) -> Lead:
    fields: dict[str, Any] = {
        "lead_type": Lead.LeadType.RFQ,
        "name": name,
        "email": f"{name.lower()}@klimat.ru",
        "phone": "+7 900 111-22-33",
        "company": "Климат-Сервис",
        "message": "Нужен привод Belimo для вентиляции, 10 штук",
        "status": Lead.LeadStatus.NEW,
        **extra,
    }
    return Lead.objects.create(**fields)


def _labels(card: Any) -> list[str]:
    return [button.label for button in card.buttons]


@pytest.mark.django_db
def test_free_new_lead_asks_to_take_it() -> None:
    manager = _manager("lc-free")
    card = build_lead_card(_lead(), manager)

    assert card.state == "free"
    assert card.buttons[0].label == "Взять в работу"
    assert card.buttons[0].post is True
    assert card.buttons[0].primary is True
    assert "Позвонить" not in _labels(card)


@pytest.mark.django_db
def test_my_lead_without_quote_offers_call_quote_reply_and_close() -> None:
    manager = _manager("lc-mine")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)

    card = build_lead_card(lead, manager)

    assert card.state == "contact"
    assert _labels(card) == ["Позвонить", "Создать КП", "Ответить клиенту", "Закрыть заявку"]
    assert card.buttons[0].url == "tel:+79001112233"
    assert card.buttons[0].primary is True


@pytest.mark.django_db
def test_without_phone_the_quote_becomes_the_primary_step() -> None:
    manager = _manager("lc-nophone")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS, phone="")

    card = build_lead_card(lead, manager)

    assert "Позвонить" not in _labels(card)
    assert card.buttons[0].label == "Создать КП"
    assert card.buttons[0].primary is True


@pytest.mark.django_db
def test_draft_quote_asks_to_issue_it() -> None:
    manager = _manager("lc-draft")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    quote = Quote.objects.create(client=lead.client, lead=lead, created_by=manager)

    card = build_lead_card(lead, manager)

    assert card.state == "draft_quote"
    assert card.buttons[0].url == reverse("admin:crm_quote_change", args=[quote.pk])
    assert "Выдать клиенту" in card.hint


@pytest.mark.django_db
def test_sent_quote_means_waiting_for_the_client() -> None:
    manager = _manager("lc-sent")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    Quote.objects.create(client=lead.client, lead=lead, status=QuoteStatus.SENT, created_by=manager)

    card = build_lead_card(lead, manager)

    assert card.state == "waiting"
    assert "ждём ответа" in card.headline


@pytest.mark.django_db
def test_closed_lead_has_no_close_button() -> None:
    manager = _manager("lc-done")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.DONE)

    card = build_lead_card(lead, manager)

    assert card.state == "done"
    assert "Закрыть заявку" not in _labels(card)


@pytest.mark.django_db
def test_colleagues_lead_is_read_only_for_a_manager() -> None:
    manager = _manager("lc-me")
    other = _manager("lc-boss")
    lead = _lead(assignee=other, status=Lead.LeadStatus.IN_PROGRESS)

    card = build_lead_card(lead, manager)

    assert card.state == "other"
    assert card.buttons == []
    assert "Заявку ведёт" in card.headline


@pytest.mark.django_db
def test_page_shows_the_panel_with_words_items_and_history() -> None:
    manager = _manager("lc-page")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    LeadItem.objects.create(lead=lead, sku_code="AF24-SR", quantity=10)
    Activity.objects.create(client=lead.client, activity_type=ActivityType.NOTE, subject="Заметка", body="Просил счёт")
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("admin:leads_lead_change", args=[lead.pk])).content.decode()

    assert "Что делать сейчас" in html
    assert "Нужен привод Belimo" in html
    assert "AF24-SR × 10" in html
    assert "Просил счёт" in html
    # The panel's forms must sit outside the lead form.
    assert html.index('id="hoocon-lead-top"') < html.index('id="lead_form"')


@pytest.mark.django_db
def test_edit_mode_has_no_panel() -> None:
    manager = _manager("lc-edit")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("admin:leads_lead_change", args=[lead.pk]) + "?edit=1").content.decode()

    assert "hoocon-lead-top" not in html


@pytest.mark.django_db
def test_close_button_finishes_the_lead() -> None:
    manager = _manager("lc-close")
    lead = _lead(assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)

    response = http.post(reverse("crm-workspace-close-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert response.status_code == 302
    assert lead.status == Lead.LeadStatus.DONE


@pytest.mark.django_db
def test_close_is_post_only_and_hidden_for_colleagues() -> None:
    manager = _manager("lc-guard")
    other = _manager("lc-owner")
    lead = _lead(assignee=other, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)
    url = reverse("crm-workspace-close-lead", args=[lead.pk])

    assert http.get(url).status_code == 405
    assert http.post(url).status_code == 404
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
