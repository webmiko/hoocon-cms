"""Company card: action bar, next step and one history feed."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.company_card import (
    NEXT_STEP_HOUR,
    build_company_card,
    next_step_target,
    primary_person,
)
from crm.models import Activity, ActivityType, Client, Company, Quote, QuoteStatus

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _company(manager: User, name: str = "Климат-Сервис") -> Company:
    return Company.objects.create(name=name, assignee=manager, phone="+7 (495) 123-45-67")


def _person(company: Company, manager: User, email: str = "ivan@klimat.ru") -> Client:
    return Client.objects.create(name="Иван", email=email, company_ref=company, assignee=manager)


def test_next_step_target_is_working_morning() -> None:
    target = timezone.localtime(next_step_target(3))
    assert target.hour == NEXT_STEP_HOUR
    assert target.minute == 0
    assert (target.date() - timezone.localdate()).days == 3


@pytest.mark.django_db
def test_primary_person_prefers_a_real_mailbox_over_a_call_stub() -> None:
    manager = _manager("cc-primary")
    company = _company(manager)
    _person(company, manager, "stub@call.invalid")
    real = _person(company, manager, "real@klimat.ru")

    assert primary_person(company, manager) == real


@pytest.mark.django_db
def test_feed_mixes_notes_and_quotes_newest_first() -> None:
    manager = _manager("cc-feed")
    company = _company(manager)
    person = _person(company, manager)
    old = Activity.objects.create(
        client=person, activity_type=ActivityType.NOTE, subject="Заметка", body="Просил цены"
    )
    Activity.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
    Quote.objects.create(client=person, status=QuoteStatus.SENT, sent_at=timezone.now() - timedelta(hours=1))

    card = build_company_card(company, manager)

    assert [item.kind for item in card["feed"]] == ["quote", "note"]
    assert card["actions"]["call"] == "+74951234567"
    assert card["actions"]["write"].endswith(f"/{person.pk}/compose-email/")
    assert card["actions"]["quote"].endswith(f"?client={person.pk}")


@pytest.mark.django_db
def test_company_without_people_has_no_write_or_quote_button() -> None:
    manager = _manager("cc-empty")
    company = _company(manager)

    card = build_company_card(company, manager)

    assert card["feed"] == []
    assert card["actions"]["write"] == ""
    assert card["actions"]["quote"] == ""
    assert card["can_note"] is False
    assert card["next_step"]["state"] == "none"


@pytest.mark.django_db
def test_overdue_next_step_is_flagged() -> None:
    manager = _manager("cc-overdue")
    company = _company(manager)
    company.next_contact_at = timezone.now() - timedelta(days=2)
    company.save()

    assert build_company_card(company, manager)["next_step"]["state"] == "overdue"


@pytest.mark.django_db
def test_company_page_shows_the_panel() -> None:
    manager = _manager("cc-page")
    company = _company(manager)
    person = _person(company, manager)
    Activity.objects.create(client=person, activity_type=ActivityType.NOTE, subject="Заметка", body="Ждёт КП")
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:crm_company_change", args=[company.pk]))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Следующий шаг" in html
    assert "История работы с клиентом" in html
    assert "Ждёт КП" in html
    assert "Позвонить" in html
    # Its forms must not sit inside the company form (nested forms are dropped).
    assert html.index('id="hoocon-card-top"') < html.index('id="company_form"')


@pytest.mark.django_db
def test_next_step_buttons_set_the_date() -> None:
    manager = _manager("cc-step")
    company = _company(manager)
    http = HttpClient()
    http.force_login(manager)

    response = http.post(reverse("crm-workspace-company-next-step", args=[company.pk]), {"days": "3"})

    company.refresh_from_db()
    assert response.status_code == 302
    assert company.next_contact_at is not None
    assert (timezone.localtime(company.next_contact_at).date() - timezone.localdate()).days == 3


@pytest.mark.django_db
def test_next_step_rejects_arbitrary_days_and_can_be_cleared() -> None:
    manager = _manager("cc-step-bad")
    company = _company(manager)
    company.next_contact_at = timezone.now() + timedelta(days=1)
    company.save()
    http = HttpClient()
    http.force_login(manager)
    url = reverse("crm-workspace-company-next-step", args=[company.pk])

    http.post(url, {"days": "9999"})
    company.refresh_from_db()
    assert company.next_contact_at is not None

    http.post(url, {"clear": "1"})
    company.refresh_from_db()
    assert company.next_contact_at is None


@pytest.mark.django_db
def test_note_is_saved_on_the_primary_person() -> None:
    manager = _manager("cc-note")
    company = _company(manager)
    person = _person(company, manager)
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "  Обещали КП до пятницы  "})

    note = Activity.objects.get(client=person)
    assert note.body == "Обещали КП до пятницы"
    assert note.author_id == manager.pk
    assert note.activity_type == ActivityType.NOTE


@pytest.mark.django_db
def test_empty_note_is_not_saved() -> None:
    manager = _manager("cc-note-empty")
    company = _company(manager)
    person = _person(company, manager)
    http = HttpClient()
    http.force_login(manager)

    http.post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "   "})

    assert not Activity.objects.filter(client=person).exists()


@pytest.mark.django_db
def test_colleagues_company_cannot_be_changed_from_the_panel() -> None:
    manager = _manager("cc-mine")
    other = _manager("cc-other")
    company = _company(other, "Чужая")
    _person(company, other)
    http = HttpClient()
    http.force_login(manager)

    step = http.post(reverse("crm-workspace-company-next-step", args=[company.pk]), {"days": "1"})
    note = http.post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "взлом"})

    assert step.status_code == 404
    assert note.status_code == 404
    assert not Activity.objects.exists()
