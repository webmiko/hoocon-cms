"""Moved dates settle overdue calls, and «Завершить» removes what was handled outside the CRM."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Client, Company, PlannedTouch, PlannedTouchStatus
from crm.today import build_today_board
from crm.workspace import build_workspace
from leads.models import Lead

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _login(user: User) -> HttpClient:
    http = HttpClient()
    http.force_login(user)
    return http


def _firm(manager: User, name: str = "ООО ПРОМВЕНТКЛИМАТ", **fields: Any) -> Company:
    return Company.objects.create(name=name, assignee=manager, phone="+7 495 123-45-67", **fields)


def _overdue_call(company: Company, key: str, days_ago: int = 3, **fields: Any) -> PlannedTouch:
    return PlannedTouch.objects.create(
        company=company,
        starts_at=timezone.now() - timedelta(days=days_ago),
        title="Перезвонить",
        dedupe_key=key,
        **fields,
    )


def _ids(board: dict[str, Any] | None) -> list[int]:
    assert board is not None
    return [item["id"] for group in board["groups"] for item in group["items"]]


@pytest.mark.django_db
def test_moving_the_next_step_settles_the_overdue_call() -> None:
    me = _manager("wf-step")
    company = _firm(me)
    latest = _overdue_call(company, "wf-step-1", days_ago=1)
    older = _overdue_call(company, "wf-step-2", days_ago=5)
    assert _ids(build_today_board(me)) == [older.pk, latest.pk]

    _login(me).post(reverse("crm-workspace-company-next-step", args=[company.pk]), {"days": "3"})

    latest.refresh_from_db()
    older.refresh_from_db()
    assert latest.status == PlannedTouchStatus.RESCHEDULED
    assert latest.starts_at > timezone.now()
    assert older.status == PlannedTouchStatus.DONE
    assert _ids(build_today_board(me)) == []


@pytest.mark.django_db
def test_moving_the_next_step_leaves_a_colleagues_call_alone() -> None:
    me, owner = _manager("wf-step-me"), _manager("wf-step-owner")
    company = Company.objects.create(name="Свободная", phone="+7 495 123-45-67")
    theirs = _overdue_call(company, "wf-step-3", assignee=owner)

    _login(me).post(reverse("crm-workspace-company-next-step", args=[company.pk]), {"days": "3"})

    theirs.refresh_from_db()
    assert theirs.status == PlannedTouchStatus.PLANNED


@pytest.mark.django_db
def test_a_later_next_step_hides_the_old_overdue_call() -> None:
    """The manager moved the date by hand on the firm: the old call is the same promise."""
    me = _manager("wf-super")
    company = _firm(me, next_contact_at=timezone.now() + timedelta(days=2))
    touch = _overdue_call(company, "wf-super-1")

    assert touch.pk not in _ids(build_today_board(me))
    workspace = build_workspace(me)
    assert all(section.key != "calls" for section in workspace["sections"])


@pytest.mark.django_db
def test_without_a_later_next_step_the_call_stays_overdue() -> None:
    me = _manager("wf-stays")
    company = _firm(me, next_contact_at=timezone.now() - timedelta(days=1))
    touch = _overdue_call(company, "wf-stays-1")

    assert touch.pk in _ids(build_today_board(me))


@pytest.mark.django_db
def test_every_queue_row_that_can_be_closed_has_a_finish_button() -> None:
    me = _manager("wf-rows")
    Lead.objects.create(name="Новая", email="wf-new@example.com", message="Нужны клапаны для котельной")
    Lead.objects.create(
        name="В работе",
        email="wf-work@example.com",
        message="Нужны клапаны для котельной",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=me,
    )
    company = _firm(me, "Пора", next_contact_at=timezone.now() - timedelta(days=2))
    _overdue_call(_firm(me, "Со звонком"), "wf-rows-1")

    sections = {section.key: section for section in build_workspace(me)["sections"]}

    assert sections["new-leads"].rows[0].finish is not None
    assert sections["in-work"].rows[0].finish is not None
    assert sections["calls"].rows[0].finish is not None
    assert sections["follow-ups"].rows[0].finish is not None
    assert sections["follow-ups"].rows[0].finish.url.endswith(f"/{company.pk}/")
    assert sections["new-leads"].rows[0].finish.confirm


@pytest.mark.django_db
def test_workspace_page_shows_finish_with_a_confirmation() -> None:
    me = _manager("wf-page")
    Lead.objects.create(name="Мария", email="wf-page@example.com", message="Нужны клапаны для котельной")

    html = _login(me).get(reverse("crm-workspace")).content.decode()

    assert "Завершить" in html
    assert "confirm(" in html
    assert "1С" in html


@pytest.mark.django_db
def test_finish_lead_closes_a_free_lead_and_takes_it() -> None:
    me = _manager("wf-lead")
    lead = Lead.objects.create(name="Из 1С", email="wf-1c@example.com", message="Нужны клапаны для котельной")

    response = _login(me).post(reverse("crm-workspace-finish-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert response.status_code == 302
    assert lead.status == Lead.LeadStatus.DONE
    assert lead.assignee_id == me.pk
    assert lead.processed_by_id == me.pk


@pytest.mark.django_db
def test_finish_lead_closes_my_own_lead_and_it_leaves_the_queue() -> None:
    me = _manager("wf-own")
    lead = Lead.objects.create(
        name="Моя",
        email="wf-own@example.com",
        message="Нужны клапаны для котельной",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=me,
    )

    _login(me).post(reverse("crm-workspace-finish-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.DONE
    assert all(section.key != "in-work" for section in build_workspace(me)["sections"])


@pytest.mark.django_db
def test_finish_lead_refuses_a_colleagues_lead_even_when_it_is_in_scope() -> None:
    me, owner = _manager("wf-lead-me"), _manager("wf-lead-owner")
    person = Client.objects.create(name="Мой клиент", email="wf-mine@klimat.ru", assignee=me)
    lead = Lead.objects.create(
        name="Чужая",
        email="wf-theirs@example.com",
        message="Нужны клапаны для котельной",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=owner,
        client=person,
    )

    _login(me).post(reverse("crm-workspace-finish-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    assert lead.assignee_id == owner.pk


@pytest.mark.django_db
def test_finish_endpoints_are_post_only_and_hide_a_colleagues_objects() -> None:
    me, owner = _manager("wf-guard"), _manager("wf-guard-owner")
    theirs_firm = _firm(owner, "Чужая фирма")
    theirs_call = _overdue_call(theirs_firm, "wf-guard-1", assignee=owner)
    http = _login(me)

    assert http.get(reverse("crm-workspace-finish-call", args=[theirs_call.pk])).status_code == 405
    assert http.post(reverse("crm-workspace-finish-call", args=[theirs_call.pk])).status_code == 404
    assert http.post(reverse("crm-workspace-finish-follow-up", args=[theirs_firm.pk])).status_code == 404
    theirs_call.refresh_from_db()
    assert theirs_call.status == PlannedTouchStatus.PLANNED


@pytest.mark.django_db
def test_finish_call_closes_it_and_it_leaves_the_queue() -> None:
    me = _manager("wf-call")
    touch = _overdue_call(_firm(me), "wf-call-1")

    _login(me).post(reverse("crm-workspace-finish-call", args=[touch.pk]))

    touch.refresh_from_db()
    assert touch.status == PlannedTouchStatus.DONE
    assert _ids(build_today_board(me)) == []


@pytest.mark.django_db
def test_finish_follow_up_clears_the_date_and_settles_due_calls() -> None:
    me = _manager("wf-follow")
    company = _firm(me, next_contact_at=timezone.now() - timedelta(days=2))
    touch = _overdue_call(company, "wf-follow-1")

    _login(me).post(reverse("crm-workspace-finish-follow-up", args=[company.pk]))

    company.refresh_from_db()
    touch.refresh_from_db()
    assert company.next_contact_at is None
    assert touch.status == PlannedTouchStatus.DONE
    assert build_workspace(me)["total"] == 0
