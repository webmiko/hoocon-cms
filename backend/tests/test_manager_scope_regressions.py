"""Review findings of 2026-11-26: the new buttons must not open or change a colleague's data."""

from __future__ import annotations

import re
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
from crm.company_card import build_company_card, primary_person
from crm.models import (
    Activity,
    Client,
    Company,
    PlannedTouch,
    PlannedTouchKind,
    PlannedTouchStatus,
    Quote,
    QuoteStatus,
)
from leads.models import Lead
from supportchat.models import Conversation, ConversationStatus

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


def _free_firm_with_colleagues_person(owner: User) -> tuple[Company, Client]:
    """A free firm (visible to every manager) whose only person belongs to a colleague."""
    company = Company.objects.create(name="Свободная фирма", phone="+7 495 123-45-67")
    person = Client.objects.create(
        name="Чужой",
        email="foreign@klimat.ru",
        phone="+7 900 999-88-77",
        company_ref=company,
        assignee=owner,
    )
    return company, person


@pytest.mark.django_db
def test_note_on_a_free_firm_does_not_unlock_a_colleagues_client() -> None:
    me, owner = _manager("sr-me"), _manager("sr-owner")
    company, person = _free_firm_with_colleagues_person(owner)
    http = _login(me)
    assert http.get(reverse("admin:crm_client_change", args=[person.pk])).status_code != 200

    http.post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "Позвонил"})

    assert not Activity.objects.filter(client=person).exists()
    assert http.get(reverse("admin:crm_client_change", args=[person.pk])).status_code != 200


@pytest.mark.django_db
def test_call_result_on_a_free_firm_does_not_unlock_a_colleagues_client() -> None:
    me, owner = _manager("sr-call-me"), _manager("sr-call-owner")
    company, person = _free_firm_with_colleagues_person(owner)
    http = _login(me)

    http.post(reverse("crm-workspace-company-call-result", args=[company.pk]), {"outcome": "reached"})

    assert not Activity.objects.filter(client=person).exists()
    assert http.get(reverse("admin:crm_client_change", args=[person.pk])).status_code != 200


@pytest.mark.django_db
def test_panel_hides_a_colleagues_person_phone_and_actions() -> None:
    me, owner = _manager("sr-panel-me"), _manager("sr-panel-owner")
    company = Company.objects.create(name="Без общего телефона")
    person = Client.objects.create(
        name="Чужой",
        email="panel-foreign@klimat.ru",
        phone="+7 900 999-88-77",
        company_ref=company,
        assignee=owner,
    )

    card = build_company_card(company, me)

    assert primary_person(company, me) is None
    assert card["actions"]["call"] == ""
    assert card["actions"]["write"] == ""
    assert card["can_note"] is False
    assert f"/{person.pk}/" not in "".join(card["actions"].values())


@pytest.mark.django_db
def test_own_person_still_works_on_a_free_firm() -> None:
    me = _manager("sr-own")
    company = Company.objects.create(name="Свободная своя")
    mine = Client.objects.create(name="Мой", email="own@klimat.ru", company_ref=company, assignee=me)

    assert primary_person(company, me) == mine
    _login(me).post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "ок"})
    assert Activity.objects.filter(client=mine).count() == 1


@pytest.mark.django_db
def test_call_result_leaves_a_colleagues_planned_call_and_meetings_alone() -> None:
    me, owner = _manager("sr-tp-me"), _manager("sr-tp-owner")
    company = Company.objects.create(name="Свободная со звонком")
    Client.objects.create(name="Мой", email="tp-mine@klimat.ru", company_ref=company, assignee=me)
    due = timezone.now() - timedelta(hours=2)
    theirs = PlannedTouch.objects.create(
        company=company, assignee=owner, starts_at=due, title="Чужой звонок", dedupe_key="sr-tp-1"
    )
    meeting = PlannedTouch.objects.create(
        company=company,
        assignee=me,
        kind=PlannedTouchKind.MEETING,
        starts_at=due,
        title="Встреча",
        dedupe_key="sr-tp-2",
    )

    _login(me).post(reverse("crm-workspace-company-call-result", args=[company.pk]), {"outcome": "no_answer"})

    theirs.refresh_from_db()
    meeting.refresh_from_db()
    assert theirs.status == PlannedTouchStatus.PLANNED
    assert theirs.starts_at == due
    assert meeting.status == PlannedTouchStatus.PLANNED
    assert meeting.starts_at == due


@pytest.mark.django_db
def test_no_answer_moves_only_the_latest_due_call() -> None:
    me = _manager("sr-latest")
    company = Company.objects.create(name="Две просрочки", assignee=me)
    Client.objects.create(name="Мой", email="latest@klimat.ru", company_ref=company, assignee=me)
    old = PlannedTouch.objects.create(
        company=company,
        starts_at=timezone.now() - timedelta(days=3),
        title="Старый",
        dedupe_key="sr-latest-1",
    )
    new = PlannedTouch.objects.create(
        company=company,
        starts_at=timezone.now() - timedelta(hours=1),
        title="Новый",
        dedupe_key="sr-latest-2",
    )

    _login(me).post(reverse("crm-workspace-company-call-result", args=[company.pk]), {"outcome": "no_answer"})

    old.refresh_from_db()
    new.refresh_from_db()
    assert new.status == PlannedTouchStatus.NO_ANSWER
    assert new.starts_at > timezone.now()
    assert old.status == PlannedTouchStatus.PLANNED


def _lead(**extra: Any) -> Lead:
    return Lead.objects.create(
        name="Мария",
        email=f"sr-{Lead.objects.count()}@example.com",
        message="Нужны клапаны для котельной",
        **extra,
    )


@pytest.mark.django_db
def test_close_lead_refuses_a_lead_of_a_colleague_even_when_it_is_in_scope() -> None:
    me, owner = _manager("sr-lead-me"), _manager("sr-lead-owner")
    person = Client.objects.create(name="Мой клиент", email="sr-mine@klimat.ru", assignee=me)
    lead = _lead(assignee=owner, status=Lead.LeadStatus.IN_PROGRESS, client=person)

    _login(me).post(reverse("crm-workspace-close-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    assert lead.processed_by_id is None


@pytest.mark.django_db
def test_close_lead_asks_to_take_a_free_lead_first() -> None:
    me = _manager("sr-free")
    lead = _lead(status=Lead.LeadStatus.NEW)

    _login(me).post(reverse("crm-workspace-close-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.NEW
    assert lead.assignee_id is None


@pytest.mark.django_db
def test_head_of_sales_may_close_any_visible_lead() -> None:
    boss = User.objects.create_superuser(username="sr-boss", email="sr-boss@example.com", password="password12")
    lead = _lead(assignee=_manager("sr-boss-owner"), status=Lead.LeadStatus.IN_PROGRESS)

    _login(boss).post(reverse("crm-workspace-close-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.DONE


@pytest.mark.django_db
def test_take_chat_does_not_take_a_closed_or_already_taken_dialog() -> None:
    me, owner = _manager("sr-chat-me"), _manager("sr-chat-owner")
    closed = Conversation.objects.create(channel="web", external_user_id="sr-closed", status=ConversationStatus.CLOSED)
    taken = Conversation.objects.create(channel="web", external_user_id="sr-taken", assignee=owner)
    http = _login(me)

    http.post(reverse("crm-workspace-take-chat", args=[closed.pk]))
    http.post(reverse("crm-workspace-take-chat", args=[taken.pk]))

    closed.refresh_from_db()
    taken.refresh_from_db()
    assert closed.assignee_id is None
    assert taken.assignee_id == owner.pk


@pytest.mark.django_db
def test_close_chat_asks_for_a_rating_once() -> None:
    from unittest.mock import patch

    me = _manager("sr-rate")
    chat = Conversation.objects.create(channel="web", external_user_id="sr-rate-1", assignee=me)
    http = _login(me)

    with patch("supportchat.rating.request_client_rating") as ask:
        http.post(reverse("crm-workspace-close-chat", args=[chat.pk]))
        http.post(reverse("crm-workspace-close-chat", args=[chat.pk]))

    assert ask.call_count == 1


@pytest.mark.django_db
def test_enter_in_the_quote_form_only_saves_never_issues() -> None:
    """The first submit button of the form is the default one for Enter."""
    me = _manager("sr-enter")
    person = Client.objects.create(name="Иван", email="enter@klimat.ru", assignee=me)
    quote = Quote.objects.create(client=person, created_by=me)
    sent = Quote.objects.create(client=person, created_by=me, status=QuoteStatus.SENT)
    http = _login(me)

    for item in (quote, sent):
        html = http.get(reverse("admin:crm_quote_change", args=[item.pk])).content.decode()
        first = re.search(r'<button[^>]*type="submit"[^>]*>', html[html.index('id="quote_form"') :])
        assert first is not None
        assert 'name="_continue"' in first.group(0), item.status
        assert "_issue_quote" not in first.group(0)


@pytest.mark.django_db
def test_non_numeric_quote_id_is_not_a_server_error() -> None:
    me = _manager("sr-abc")

    response = _login(me).get("/admin/crm/quote/abc/change/")

    assert response.status_code < 500


@pytest.mark.django_db
def test_own_firm_keeps_working_when_its_people_have_no_manager_yet() -> None:
    """Round 2: closing the colleagues' hole must not silence the manager's own firm."""
    me = _manager("sr-own-firm")
    company = Company.objects.create(name="Моя фирма с людьми без ответственного", assignee=me)
    person = Client.objects.create(name="Без ответственного", email="nobody@klimat.ru", company_ref=company)
    http = _login(me)

    assert primary_person(company, me) == person
    http.post(reverse("crm-workspace-company-note", args=[company.pk]), {"body": "Обсудили цену"})
    http.post(
        reverse("crm-workspace-company-call-result", args=[company.pk]), {"outcome": "reached", "note": "Просил КП"}
    )

    assert Activity.objects.filter(client=person).count() == 2
    assert build_company_card(company, me)["can_note"] is True


@pytest.mark.django_db
def test_own_firm_still_hides_a_colleagues_person() -> None:
    me, owner = _manager("sr-own-hide"), _manager("sr-own-hide-owner")
    company = Company.objects.create(name="Моя фирма, но человек чужой", assignee=me)
    Client.objects.create(name="Чужой", email="own-foreign@klimat.ru", company_ref=company, assignee=owner)

    assert primary_person(company, me) is None


@pytest.mark.django_db
def test_free_firm_does_not_expose_unassigned_people_to_a_note() -> None:
    me = _manager("sr-free-unassigned")
    company = Company.objects.create(name="Свободная с нейтральным человеком")
    Client.objects.create(name="Ничей", email="free-unassigned@klimat.ru", company_ref=company)

    assert primary_person(company, me) is None


@pytest.mark.django_db
def test_lost_note_text_is_reported_to_the_manager() -> None:
    me = _manager("sr-lost")
    company = Company.objects.create(name="Без людей", assignee=me)

    response = _login(me).post(
        reverse("crm-workspace-company-call-result", args=[company.pk]),
        {"outcome": "reached", "note": "Важная договорённость"},
        follow=True,
    )

    assert "текст не сохранён" in response.content.decode()
