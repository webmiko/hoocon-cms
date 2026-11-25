"""Contact page panel: actions, one history and a quick note."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Activity, ActivityType, Client, Company, Quote
from crm.person_card import build_person_card

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _person(manager: User, email: str = "ivan@klimat.ru", **fields: object) -> Client:
    company = Company.objects.create(name=f"Климат-Сервис {email}", assignee=manager)
    return Client.objects.create(
        name="Иван",
        email=email,
        phone="+7 900 111-22-33",
        company_ref=company,
        assignee=manager,
        **fields,
    )


@pytest.mark.django_db
def test_panel_offers_the_daily_actions() -> None:
    manager = _manager("pc-actions")
    person = _person(manager)

    card = build_person_card(person, manager)

    assert card.call_url.endswith(f"/{person.pk}/call-client/")
    assert card.write_url.endswith(f"/{person.pk}/compose-email/")
    assert card.quote_url.endswith(f"?client={person.pk}")
    assert card.company_name == "Климат-Сервис ivan@klimat.ru"
    assert card.result_url.endswith("#hoocon-card-top")
    assert "Климат-Сервис ivan@klimat.ru" in card.chips


@pytest.mark.django_db
def test_stub_mailbox_hides_write_and_explains_why() -> None:
    manager = _manager("pc-stub")
    person = _person(manager, email="79001112233@call.invalid")

    card = build_person_card(person, manager)

    assert card.write_url == ""
    assert card.stub_mail is True
    assert "79001112233@call.invalid" not in card.chips


@pytest.mark.django_db
def test_page_shows_the_panel_outside_the_form_with_history() -> None:
    manager = _manager("pc-page")
    person = _person(manager)
    Activity.objects.create(client=person, activity_type=ActivityType.NOTE, subject="Заметка", body="Ждёт счёт")
    Quote.objects.create(client=person, created_by=manager)
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("admin:crm_client_change", args=[person.pk])).content.decode()

    assert "История с этим человеком" in html
    assert "Ждёт счёт" in html
    assert "Позвонить" in html
    assert html.index('id="hoocon-person-top"') < html.index('id="client_form"')


@pytest.mark.django_db
def test_add_page_has_no_panel() -> None:
    manager = _manager("pc-add")
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:crm_client_add"))

    assert response.status_code == 200
    assert "hoocon-person-top" not in response.content.decode()


@pytest.mark.django_db
def test_note_is_saved_on_this_person() -> None:
    manager = _manager("pc-note")
    person = _person(manager)
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-person-note", args=[person.pk]), {"body": "  Просил КП до пятницы "})

    note = Activity.objects.get(client=person)
    assert note.body == "Просил КП до пятницы"
    assert note.author_id == manager.pk


@pytest.mark.django_db
def test_empty_note_is_ignored_and_colleagues_person_is_hidden() -> None:
    manager = _manager("pc-guard")
    other = _manager("pc-owner")
    mine = _person(manager, email="mine@klimat.ru")
    theirs = _person(other, email="theirs@klimat.ru")
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-person-note", args=[mine.pk]), {"body": "   "})
    stolen = http.post(reverse("crm-workspace-person-note", args=[theirs.pk]), {"body": "взлом"})

    assert stolen.status_code == 404
    assert not Activity.objects.exists()


@pytest.mark.django_db
def test_top_toolbar_is_gone_and_its_leftovers_moved_into_the_panel() -> None:
    manager = _manager("pc-toolbar")
    person = _person(manager)
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("admin:crm_client_change", args=[person.pk])).content.decode()

    assert "Заявка из Excel-спецификации" in html
    assert "Кто и когда менял карточку" in html
    # The old header list repeated the panel's actions; it must not come back.
    assert "data-hoocon-phone-action-list" not in html
    assert html.count(f"/admin/crm/client/{person.pk}/compose-email/") == 1
    assert html.count(f"/admin/crm/client/{person.pk}/call-client/") == 1


@pytest.mark.django_db
def test_orders_appear_in_the_history_and_in_the_jump_links() -> None:
    from cabinet.models import Order

    manager = _manager("pc-orders")
    person = _person(manager)
    Order.objects.create(client=person, number="З-КП-1", status="accepted")
    http = HttpClient()
    http.force_login(manager)

    card = build_person_card(person, manager)
    html = http.get(reverse("admin:crm_client_change", args=[person.pk])).content.decode()
    counts = {section["tab"]: section["count"] for section in card.sections}

    assert counts["orders"] == 1
    assert any(item.kind == "order" and item.title == "З-КП-1" for item in card.feed)
    assert "Открыть:" in html
    assert "activeTab = 'orders'" in html
    assert "З-КП-1" in html


@pytest.mark.django_db
def test_colleagues_orders_stay_out_of_the_feed_and_counts() -> None:
    from cabinet.models import Order

    manager = _manager("pc-ord-me")
    other = _manager("pc-ord-other")
    mine = _person(manager, email="ord-mine@klimat.ru")
    theirs = _person(other, email="ord-theirs@klimat.ru")
    Order.objects.create(client=theirs, number="З-ЧУЖОЙ", status="accepted")

    card = build_person_card(mine, manager)

    assert {section["tab"]: section["count"] for section in card.sections}["orders"] == 0
    assert all(item.title != "З-ЧУЖОЙ" for item in card.feed)
