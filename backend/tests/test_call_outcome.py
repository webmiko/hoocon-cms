"""Call result in one touch: history, planned call and next step stay in sync."""

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
from crm.models import Activity, ActivityType, Client, Company, PlannedTouch, PlannedTouchStatus
from crm.today import build_today_board

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _setup(name: str, *, person: bool = True) -> tuple[User, Company, HttpClient]:
    manager = _manager(name)
    company = Company.objects.create(name=f"Фирма {name}", assignee=manager, phone="+7 495 123-45-67")
    if person:
        Client.objects.create(name="Иван", email=f"{name}@klimat.ru", company_ref=company, assignee=manager)
    http = HttpClient()
    http.force_login(manager)
    return manager, company, http


def _due_touch(company: Company, key: str, **fields: object) -> PlannedTouch:
    return PlannedTouch.objects.create(
        company=company,
        starts_at=timezone.now() - timedelta(hours=2),
        title="Звонок",
        dedupe_key=key,
        **fields,
    )


def _url(company: Company) -> str:
    return reverse("crm-workspace-company-call-result", args=[company.pk])


@pytest.mark.django_db
def test_reached_logs_the_call_and_closes_the_planned_one() -> None:
    manager, company, http = _setup("co-reached")
    touch = _due_touch(company, "co-reached-1")

    response = http.post(_url(company), {"outcome": "reached", "note": "Просил цены на приводы"})

    touch.refresh_from_db()
    note = Activity.objects.get()
    assert response.status_code == 302
    assert note.activity_type == ActivityType.CALL
    assert note.subject == "Звонок: Дозвонился"
    assert note.body == "Просил цены на приводы"
    assert note.author_id == manager.pk
    assert touch.status == PlannedTouchStatus.REACHED
    assert build_today_board(manager) is None or build_today_board(manager)["empty"] is True


@pytest.mark.django_db
def test_no_answer_moves_the_call_to_tomorrow_morning() -> None:
    _manager_user, company, http = _setup("co-noanswer")
    touch = _due_touch(company, "co-noanswer-1")

    http.post(_url(company), {"outcome": "no_answer"})

    touch.refresh_from_db()
    company.refresh_from_db()
    expected = (timezone.localtime() + timedelta(days=1)).date()
    assert touch.status == PlannedTouchStatus.NO_ANSWER
    assert timezone.localtime(touch.starts_at).date() == expected
    assert timezone.localtime(touch.starts_at).hour == 10
    assert timezone.localtime(company.next_contact_at).date() == expected


@pytest.mark.django_db
def test_callback_uses_the_chosen_day() -> None:
    _manager_user, company, http = _setup("co-callback")

    http.post(_url(company), {"outcome": "callback", "days": "3"})

    company.refresh_from_db()
    assert (timezone.localtime(company.next_contact_at).date() - timezone.localdate()).days == 3


@pytest.mark.django_db
def test_reached_without_a_date_keeps_the_existing_next_step() -> None:
    _manager_user, company, http = _setup("co-keep")
    company.next_contact_at = timezone.now() + timedelta(days=5)
    company.save()
    before = company.next_contact_at

    http.post(_url(company), {"outcome": "reached"})

    company.refresh_from_db()
    assert company.next_contact_at == before


@pytest.mark.django_db
def test_need_quote_opens_a_new_quote_for_the_person() -> None:
    _manager_user, company, http = _setup("co-quote")
    person = Client.objects.get(company_ref=company)

    response = http.post(_url(company), {"outcome": "need_quote"})

    assert response.status_code == 302
    assert response.url == reverse("admin:crm_quote_add") + f"?client={person.pk}"


@pytest.mark.django_db
def test_future_planned_call_is_left_alone() -> None:
    _manager_user, company, http = _setup("co-future")
    future = PlannedTouch.objects.create(
        company=company,
        starts_at=timezone.now() + timedelta(days=4),
        title="Позже",
        dedupe_key="co-future-1",
    )

    http.post(_url(company), {"outcome": "reached"})

    future.refresh_from_db()
    assert future.status == PlannedTouchStatus.PLANNED


@pytest.mark.django_db
def test_bad_outcome_or_days_change_nothing() -> None:
    _manager_user, company, http = _setup("co-bad")

    http.post(_url(company), {"outcome": "hack"})
    http.post(_url(company), {"outcome": "reached", "days": "9999"})
    http.post(_url(company), {"outcome": "reached", "days": "abc"})

    company.refresh_from_db()
    assert not Activity.objects.exists()
    assert company.next_contact_at is None


@pytest.mark.django_db
def test_company_without_people_still_gets_the_next_step() -> None:
    _manager_user, company, http = _setup("co-nobody", person=False)

    http.post(_url(company), {"outcome": "no_answer"})

    company.refresh_from_db()
    assert not Activity.objects.exists()
    assert company.next_contact_at is not None


@pytest.mark.django_db
def test_colleagues_company_is_not_found() -> None:
    _manager_user, company, _http = _setup("co-owner")
    other = _manager("co-intruder")
    http = HttpClient()
    http.force_login(other)

    response = http.post(_url(company), {"outcome": "reached"})

    assert response.status_code == 404
    assert not Activity.objects.exists()


@pytest.mark.django_db
def test_settled_call_does_not_stay_in_the_overdue_queue() -> None:
    manager, company, _http = _setup("co-board")
    _due_touch(company, "co-board-1", status=PlannedTouchStatus.REACHED)
    _due_touch(company, "co-board-2", status=PlannedTouchStatus.DONE)
    open_one = _due_touch(company, "co-board-3")

    board = build_today_board(manager)

    names = [item["id"] for group in board["groups"] for item in group["items"]]
    assert names == [open_one.pk]


@pytest.mark.django_db
def test_company_page_has_the_result_form_outside_the_company_form() -> None:
    _manager_user, company, http = _setup("co-page")

    html = http.get(reverse("admin:crm_company_change", args=[company.pk])).content.decode()

    assert "Записать итог" in html
    assert 'name="outcome"' in html
    assert html.index('id="hoocon-call-result"') < html.index('id="company_form"')
