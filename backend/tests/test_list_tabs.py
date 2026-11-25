"""One-click tabs above the lists of leads, firms and offers."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import QueryDict
from django.test import Client as HttpClient
from django.urls import reverse
from django.utils import timezone

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.list_tabs import TabSpec, build_list_tabs
from crm.models import Client, Company, Quote, QuoteStatus
from leads.models import Lead

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _lead(name: str, **extra: Any) -> Lead:
    fields: dict[str, Any] = {"status": Lead.LeadStatus.NEW, "message": "Нужны клапаны для котельной", **extra}
    return Lead.objects.create(name=name, email=f"{name.lower()}@example.com", **fields)


def _by_label(tabs: list[Any]) -> dict[str, Any]:
    return {tab.label: tab for tab in tabs}


@pytest.mark.django_db
def test_tabs_count_rows_and_mark_the_active_one() -> None:
    _lead("Новая1")
    _lead("Новая2")
    _lead("Готова", status=Lead.LeadStatus.DONE)
    specs = [
        TabSpec("Все"),
        TabSpec("Новые", {"status__exact": "new"}, Q(status=Lead.LeadStatus.NEW)),
        TabSpec("Завершённые", {"status__exact": "done"}, Q(status=Lead.LeadStatus.DONE)),
    ]

    tabs = _by_label(build_list_tabs(QueryDict("status__exact=new"), Lead.objects.all(), specs))

    assert tabs["Все"].count == 3
    assert tabs["Новые"].count == 2
    assert tabs["Завершённые"].count == 1
    assert tabs["Новые"].active is True
    assert tabs["Все"].active is False


@pytest.mark.django_db
def test_reset_tab_is_active_without_filters_and_links_keep_the_search() -> None:
    specs = [TabSpec("Все"), TabSpec("Новые", {"status__exact": "new"}, Q(status=Lead.LeadStatus.NEW))]

    tabs = _by_label(build_list_tabs(QueryDict("q=belimo&p=3"), Lead.objects.all(), specs))

    assert tabs["Все"].active is True
    assert tabs["Новые"].url == "?q=belimo&status__exact=new"
    assert tabs["Все"].url == "?q=belimo"


@pytest.mark.django_db
def test_leads_page_shows_tabs_with_my_counts_only() -> None:
    manager = _manager("lt-lead")
    other = _manager("lt-other")
    _lead("Свободная")
    _lead("Моя", assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    _lead("Чужая", assignee=other, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:leads_lead_changelist"))
    tabs = _by_label(response.context_data["hoocon_tabs"])

    assert response.status_code == 200
    assert tabs["Новые"].count == 1
    assert tabs["Мои в работе"].count == 1
    # A colleague's lead is outside the manager's scope, so it is in no count.
    assert tabs["Все"].count == 2
    assert "hoocon-tabs" in response.content.decode()


@pytest.mark.django_db
def test_tab_links_open_a_valid_list() -> None:
    manager = _manager("lt-links")
    _lead("Моя", assignee=manager, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)

    tabs = http.get(reverse("admin:leads_lead_changelist")).context_data["hoocon_tabs"]

    for tab in tabs:
        response = http.get(reverse("admin:leads_lead_changelist") + tab.url)
        assert response.status_code == 200, tab.label
    mine = _by_label(tabs)["Мои в работе"]
    html = http.get(reverse("admin:leads_lead_changelist") + mine.url).content.decode()
    assert "Моя" in html


@pytest.mark.django_db
def test_company_tabs_split_mine_overdue_and_free() -> None:
    manager = _manager("lt-company")
    Company.objects.create(name="Моя", assignee=manager)
    Company.objects.create(name="Просрочена", assignee=manager, next_contact_at=timezone.now() - timedelta(days=2))
    Company.objects.create(name="Свободная")
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:crm_company_changelist"))
    tabs = _by_label(response.context_data["hoocon_tabs"])

    assert tabs["Мои"].count == 2
    assert tabs["Пора вернуться"].count == 1
    assert tabs["Свободные"].count == 1
    for tab in tabs.values():
        assert http.get(reverse("admin:crm_company_changelist") + tab.url).status_code == 200, tab.label


@pytest.mark.django_db
def test_quote_tabs_follow_status_and_work() -> None:
    manager = _manager("lt-quote")
    person = Client.objects.create(name="Иван", email="lt-quote@klimat.ru", assignee=manager)
    Quote.objects.create(client=person, status=QuoteStatus.DRAFT)
    Quote.objects.create(client=person, status=QuoteStatus.SENT)
    Quote.objects.create(client=person, status=QuoteStatus.SENT)
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("admin:crm_quote_changelist"))
    tabs = _by_label(response.context_data["hoocon_tabs"])

    assert tabs["Черновики"].count == 1
    assert tabs["Ждут ответа"].count == 2
    assert "Выдать клиенту" in response.content.decode()
    for tab in tabs.values():
        assert http.get(reverse("admin:crm_quote_changelist") + tab.url).status_code == 200, tab.label
