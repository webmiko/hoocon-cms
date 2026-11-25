"""«Мой день»: one queue of what a sales manager should do right now."""

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
from crm.models import Client, Company, Quote, QuoteStatus
from crm.workspace import build_workspace, human_wait
from leads.models import Lead

User = get_user_model()


def _manager(name: str) -> User:
    ensure_staff_groups()
    user = User.objects.create_user(username=name, email=f"{name}@example.com", password="password12", is_staff=True)
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _lead(name: str = "Иван", **extra: object) -> Lead:
    fields: dict[str, object] = {
        "status": Lead.LeadStatus.NEW,
        "message": "Нужны клапаны для котельной",
        **extra,
    }
    return Lead.objects.create(name=name, email=f"{name.lower()}@example.com", **fields)


def test_human_wait_uses_the_largest_unit() -> None:
    assert human_wait(timedelta(seconds=20)) == "только что"
    assert human_wait(timedelta(minutes=12)) == "12 мин"
    assert human_wait(timedelta(hours=3)) == "3 ч"
    assert human_wait(timedelta(days=2, hours=5)) == "2 дн."


@pytest.mark.django_db
def test_new_lead_is_the_first_thing_to_do() -> None:
    manager = _manager("ws-first")
    _lead("Пётр")

    data = build_workspace(manager)

    assert data["total"] == 1
    assert data["first"].title == "Пётр"
    assert data["first"].primary.label == "Взять в работу"
    assert data["first"].primary.post is True


@pytest.mark.django_db
def test_colleagues_lead_is_not_in_my_queue() -> None:
    manager = _manager("ws-mine")
    other = _manager("ws-other")
    _lead("Чужой", assignee=other, status=Lead.LeadStatus.IN_PROGRESS)

    data = build_workspace(manager)

    assert data["first"] is None
    assert data["total"] == 0


@pytest.mark.django_db
def test_silent_quote_waits_in_the_queue() -> None:
    manager = _manager("ws-quote")
    client = Client.objects.create(name="Ольга", email="olga@example.com", assignee=manager)
    Quote.objects.create(
        client=client,
        status=QuoteStatus.SENT,
        sent_at=timezone.now() - timedelta(days=5),
    )
    fresh = Client.objects.create(name="Свежий", email="fresh@example.com", assignee=manager)
    Quote.objects.create(client=fresh, status=QuoteStatus.SENT, sent_at=timezone.now() - timedelta(hours=5))

    data = build_workspace(manager)

    section = next(item for item in data["sections"] if item.key == "quotes")
    assert [row.title for row in section.rows] == ["Ольга"]
    assert section.rows[0].waiting == "5 дн."


@pytest.mark.django_db
def test_overdue_company_follow_up_is_listed_but_future_is_not() -> None:
    manager = _manager("ws-company")
    Company.objects.create(name="Пора", assignee=manager, next_contact_at=timezone.now() - timedelta(days=1))
    Company.objects.create(name="Рано", assignee=manager, next_contact_at=timezone.now() + timedelta(days=2))

    data = build_workspace(manager)

    section = next(item for item in data["sections"] if item.key == "follow-ups")
    assert [row.title for row in section.rows] == ["Пора"]


@pytest.mark.django_db
def test_page_renders_for_manager_with_start_card() -> None:
    manager = _manager("ws-page")
    _lead("Анна")
    http = HttpClient()
    http.force_login(manager)

    response = http.get(reverse("crm-workspace"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Мой день" in html
    assert "Начните с этого" in html
    assert "Анна" in html
    assert "Взять в работу" in html


@pytest.mark.django_db
def test_empty_queue_shows_the_guide_open() -> None:
    manager = _manager("ws-empty")
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("crm-workspace")).content.decode()

    assert "Всё разобрано" in html
    assert "Путь клиента в четыре шага" in html


@pytest.mark.django_db
def test_page_requires_staff_login() -> None:
    response = HttpClient().get(reverse("crm-workspace"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_take_lead_assigns_and_opens_the_lead() -> None:
    manager = _manager("ws-take")
    lead = _lead("Взять")
    http = HttpClient()
    http.force_login(manager)

    response = http.post(reverse("crm-workspace-take-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert lead.assignee_id == manager.pk
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    assert response.status_code == 302
    assert response.url == reverse("admin:leads_lead_change", args=[lead.pk])


@pytest.mark.django_db
def test_take_lead_of_a_colleague_is_not_found() -> None:
    manager = _manager("ws-steal")
    other = _manager("ws-owner")
    lead = _lead("Занят", assignee=other, status=Lead.LeadStatus.IN_PROGRESS)
    http = HttpClient()
    http.force_login(manager)

    response = http.post(reverse("crm-workspace-take-lead", args=[lead.pk]))

    lead.refresh_from_db()
    assert response.status_code == 404
    assert lead.assignee_id == other.pk


@pytest.mark.django_db
def test_take_lead_needs_post() -> None:
    manager = _manager("ws-get")
    lead = _lead("Гет")
    http = HttpClient()
    http.force_login(manager)

    assert http.get(reverse("crm-workspace-take-lead", args=[lead.pk])).status_code == 405


@pytest.mark.django_db
def test_stale_lead_does_not_take_the_start_slot() -> None:
    manager = _manager("ws-stale")
    old = _lead("Давний")
    Lead.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=60))
    _lead("Свежий")

    data = build_workspace(manager)

    assert data["first"].title == "Свежий"
    section = next(item for item in data["sections"] if item.key == "new-leads")
    assert [row.title for row in section.rows] == ["Свежий"]
    assert section.stale == 1
    assert data["stale"] == 1


@pytest.mark.django_db
def test_only_stale_backlog_still_shows_a_reminder() -> None:
    manager = _manager("ws-backlog")
    old = _lead("Давний")
    Lead.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=60))
    http = HttpClient()
    http.force_login(manager)

    html = http.get(reverse("crm-workspace")).content.decode()

    assert "Всё разобрано" in html
    assert "разобрать или закрыть" in html


@pytest.mark.django_db
def test_manager_lands_on_my_day_from_bare_admin_address() -> None:
    manager = _manager("ws-landing")
    http = HttpClient()
    http.force_login(manager)

    response = http.get("/admin/")

    assert response.status_code == 302
    assert response.url == reverse("crm-workspace")


@pytest.mark.django_db
def test_panel_stays_reachable_for_manager_with_query() -> None:
    manager = _manager("ws-panel")
    http = HttpClient()
    http.force_login(manager)

    assert http.get("/admin/?hoocon_view=dashboard").status_code == 200


@pytest.mark.django_db
def test_superuser_still_gets_the_panel() -> None:
    admin_user = User.objects.create_superuser(username="ws-root", email="ws-root@example.com", password="password12")
    http = HttpClient()
    http.force_login(admin_user)

    assert http.get("/admin/").status_code == 200


@pytest.mark.django_db
def test_menu_keeps_the_daily_path_first_and_rare_rows_apart() -> None:
    from django.test import RequestFactory

    from config.phone_settings_nav import build_phone_settings_nav

    manager = _manager("ws-sidebar")
    request = RequestFactory().get("/admin/")
    request.user = manager

    nav = build_phone_settings_nav(request)

    assert nav is not None
    assert nav["groups"][0]["id"] == "workspace"
    work = next(section for section in nav["sections"] if section["id"] == "work")
    assert [row["title"] for row in work["rows"]][:3] == ["Заявки", "Клиенты", "КП"]
    more = next(section for section in nav["sections"] if section["id"] == "work_more")
    assert "Статистика заявок" in [row["title"] for row in more["rows"]]
    assert "Статистика заявок" not in [row["title"] for row in work["rows"]]


@pytest.mark.django_db
def test_new_lead_and_chat_are_cards_with_the_clients_words() -> None:
    from supportchat.models import Conversation, Message, MessageDirection

    manager = _manager("ws-cards")
    _lead("Мария", phone="+7 900 111-22-33", message="Нужен привод Belimo для вентиляции, 10 штук")
    chat = Conversation.objects.create(
        channel="web",
        external_user_id="visitor-1",
        display_name="Посетитель",
        staff_unread_count=2,
        last_message_at=timezone.now(),
    )
    Message.objects.create(conversation=chat, direction=MessageDirection.INBOUND, body="Есть ли в наличии AF24?")
    http = HttpClient()
    http.force_login(manager)

    data = build_workspace(manager)
    html = http.get(reverse("crm-workspace")).content.decode()

    layouts = {section.key: section.layout for section in data["sections"]}
    assert layouts["new-leads"] == "cards"
    assert layouts["chats"] == "cards"
    assert html.count('<li class="hoocon-ws__card') == 2
    assert "Нужен привод Belimo" in html
    assert "+7 900 111-22-33" in html
    assert "Есть ли в наличии AF24?" in html


@pytest.mark.django_db
def test_phone_menu_stays_reachable_for_a_manager() -> None:
    """The bare /admin/ opens «Мой день»; the phone menu of sections has its own address."""
    manager = _manager("ws-phone")
    http = HttpClient()
    http.force_login(manager)

    hub = http.get("/admin/?hoocon_view=menu")
    shell = http.get(reverse("crm-workspace")).content.decode()

    assert hub.status_code == 200
    assert 'data-hoocon-phone-tab="workspace"' in shell
    assert 'data-hoocon-phone-tab="home"' not in shell
    assert "/admin/?hoocon_view=menu" in shell
    assert "Все разделы" in shell


@pytest.mark.django_db
def test_phone_tabs_for_the_head_of_sales_keep_the_panel() -> None:
    admin_user = User.objects.create_superuser(
        username="ws-phone-root", email="ws-phone-root@example.com", password="password12"
    )
    http = HttpClient()
    http.force_login(admin_user)

    shell = http.get("/admin/").content.decode()

    assert 'data-hoocon-phone-tab="home"' in shell
    assert 'data-hoocon-phone-tab="workspace"' not in shell


def test_phone_hub_back_button_does_not_hit_the_redirecting_address() -> None:
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-phone-settings.js").read_text(
        encoding="utf-8"
    )

    assert 'window.location.href = "/admin/";' not in js
    assert "hoocon_view=menu" in js
