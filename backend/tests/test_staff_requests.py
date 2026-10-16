"""Manager requests: own cards only, admin closes them, the widget can be switched off."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import Client as DjClient
from django.test import RequestFactory
from django.urls import reverse

from accounts.roles import GROUP_ADMIN, GROUP_ANALYST, GROUP_MANAGER
from config.phone_settings_nav import build_phone_settings_nav
from staffrequests.models import StaffRequest, StaffRequestSettings, StaffRequestStatus
from staffrequests.services import can_file, can_manage_queue, can_toggle
from staffrequests.widget import menu_visible

User = get_user_model()


def _user(username: str, group_name: str, *, superuser: bool = False) -> User:
    if superuser:
        user = User.objects.create_superuser(
            username=username,
            email=f"{username}@example.com",
            password="password12",
        )
    else:
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="password12",
            is_staff=True,
        )
    group, _created = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    return user


@pytest.mark.django_db
def test_anonymous_cannot_open_the_queue_and_the_switch_is_not_deleted() -> None:
    """Гость не пишет в очередь. Удаление настройки не стирает строку."""
    anon = AnonymousUser()
    assert can_file(anon) is False
    assert can_manage_queue(anon) is False
    assert can_toggle(anon) is False
    row = StaffRequestSettings.load()
    assert str(row) == "Техподдержка выключена"
    row.enabled = True
    row.save(update_fields=["enabled"])
    assert str(StaffRequestSettings.load()) == "Техподдержка включена"
    assert row.delete() == (0, {})
    assert StaffRequestSettings.objects.filter(pk=1).exists()
    assert StaffRequestSettings.load().enabled is True


def _enable() -> None:
    row = StaffRequestSettings.load()
    row.enabled = True
    row.save(update_fields=["enabled"])


@pytest.mark.django_db
def test_widget_off_hides_the_queue_and_refuses_new_requests() -> None:
    """Выключено: меню пустое, менеджер не открывает список, карточка на интеграциях есть."""
    manager = _user("req-off", GROUP_MANAGER)
    admin = _user("req-off-admin", GROUP_ADMIN, superuser=True)
    page = DjClient()
    page.force_login(manager)
    denied = page.get(reverse("admin:staffrequests_staffrequest_changelist"))
    assert denied.status_code == 403
    page.force_login(admin)
    html = page.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    assert "Техподдержка" in html
    assert "hoocon-staffreq hoocon-integrations__card" in html
    assert "hoocon-lead-stats__card hoocon-staffreq" not in html
    assert 'class="hoocon-toggle" name="enabled"' in html
    assert "Выключен" in html
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8"
    )
    hint = css.split(".hoocon-staffreq .hoocon-integrations__hint {", 1)[1].split("}", 1)[0]
    assert "margin-top: 0.85rem" in hint
    assert "margin-bottom: 0.85rem" in hint
    request = RequestFactory().get("/admin/")
    request.user = manager
    assert menu_visible(request) is False
    nav = build_phone_settings_nav(request)
    assert nav is not None
    assert "staffrequests-staffrequest" not in {row["id"] for row in nav["groups"]}


@pytest.mark.django_db
def test_manager_files_only_own_request_and_cannot_close_it() -> None:
    """Своя карточка создаётся. Чужая — 404. Статус «сделано» менеджер не ставит."""
    author = _user("req-author", GROUP_MANAGER)
    other = _user("req-other", GROUP_MANAGER)
    analyst = _user("req-analyst", GROUP_ANALYST)
    admin = _user("req-admin", GROUP_ADMIN, superuser=True)
    _enable()
    page = DjClient()
    page.force_login(analyst)
    assert page.get(reverse("admin:staffrequests_staffrequest_changelist")).status_code == 403
    page.force_login(author)
    added = page.post(
        reverse("admin:staffrequests_staffrequest_add"),
        {"kind": "bug", "title": "Фильтр заявок", "body": "Сбрасывается после сохранения", "_save": "Сохранить"},
    )
    assert added.status_code == 302
    ticket = StaffRequest.objects.get()
    assert ticket.author_id == author.pk
    assert ticket.status == StaffRequestStatus.NEW
    assert ticket.closed_at is None
    StaffRequest.objects.create(
        author=other,
        kind="question",
        title="Чужая тема",
        body="Не показывать",
    )
    listing = page.get(reverse("admin:staffrequests_staffrequest_changelist"))
    body = listing.content.decode()
    assert listing.status_code == 200
    assert "Новое 1" in body
    assert "Фильтр заявок" in body
    assert "Чужая тема" not in body
    foreign = StaffRequest.objects.get(title="Чужая тема")
    hidden = page.get(reverse("admin:staffrequests_staffrequest_change", args=[foreign.pk]))
    assert hidden.status_code == 302
    assert hidden.url.rstrip("/").endswith("/admin")
    assert "Чужая тема" not in hidden.content.decode()
    change_url = reverse("admin:staffrequests_staffrequest_change", args=[ticket.pk])
    form_html = page.get(change_url).content.decode()
    assert "replies-TOTAL_FORMS" in form_html
    closed = page.post(
        reverse("admin:staffrequests_staffrequest_change", args=[ticket.pk]),
        {
            "kind": "bug",
            "title": "Фильтр заявок",
            "body": "Сбрасывается после сохранения",
            "status": StaffRequestStatus.DONE,
            "replies-TOTAL_FORMS": "1",
            "replies-INITIAL_FORMS": "0",
            "replies-MIN_NUM_FORMS": "0",
            "replies-MAX_NUM_FORMS": "1000",
            "replies-0-body": "Проверил ещё раз",
            "replies-0-id": "",
            "replies-0-ticket": str(ticket.pk),
            "_save": "Сохранить",
        },
    )
    assert closed.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == StaffRequestStatus.NEW
    assert ticket.closed_at is None
    assert ticket.replies.get().body == "Проверил ещё раз"
    assert ticket.replies.get().author_id == author.pk
    page.force_login(admin)
    done = page.post(
        reverse("admin:staffrequests_staffrequest_change", args=[ticket.pk]),
        {
            "kind": "bug",
            "title": "Фильтр заявок",
            "body": "Сбрасывается после сохранения",
            "status": StaffRequestStatus.DONE,
            "replies-TOTAL_FORMS": "1",
            "replies-INITIAL_FORMS": "1",
            "replies-MIN_NUM_FORMS": "0",
            "replies-MAX_NUM_FORMS": "1000",
            "replies-0-body": "Проверил ещё раз",
            "replies-0-id": str(ticket.replies.get().pk),
            "replies-0-ticket": str(ticket.pk),
            "_save": "Сохранить",
        },
    )
    assert done.status_code == 302
    ticket.refresh_from_db()
    assert ticket.status == StaffRequestStatus.DONE
    assert ticket.closed_at is not None
    queue = page.get(reverse("admin:staffrequests_staffrequest_changelist")).content.decode()
    assert "Сделано 1" in queue
    assert "Чужая тема" in queue


@pytest.mark.django_db
def test_admin_toggles_the_widget_and_a_manager_cannot() -> None:
    """Админ включает виджет с «Интеграций». Менеджер этот адрес не меняет."""
    admin = _user("req-toggle", GROUP_ADMIN, superuser=True)
    manager = _user("req-toggle-mgr", GROUP_MANAGER)
    page = DjClient()
    page.force_login(manager)
    denied = page.post(reverse("admin:staffrequests_staffrequest_toggle"), {"enabled": "on"})
    assert denied.status_code == 403
    assert StaffRequestSettings.load().enabled is False
    page.force_login(admin)
    turned_on = page.post(reverse("admin:staffrequests_staffrequest_toggle"), {"enabled": "on"})
    assert turned_on.status_code == 302
    assert StaffRequestSettings.load().enabled is True
    request = RequestFactory().get("/admin/")
    request.user = manager
    assert menu_visible(request) is True
    nav = build_phone_settings_nav(request)
    assert nav is not None
    row = next(item for item in nav["groups"] if item["id"] == "staffrequests-staffrequest")
    assert row["title"] == "Техподдержка"
    assert row["section"] == "work"
    page.post(reverse("admin:staffrequests_staffrequest_toggle"), {"enabled": "on"})
    switched_off = page.post(reverse("admin:staffrequests_staffrequest_toggle"))
    assert switched_off.status_code == 302
    assert StaffRequestSettings.load().enabled is False
    assert page.get(reverse("admin:staffrequests_staffrequest_add")).status_code == 403


@pytest.mark.django_db
def test_integrations_save_posts_the_switch_outside_the_changelist_form() -> None:
    """«Сохранить» на карточке шлёт свой POST: вложенная форма внутри списка отбрасывается браузером."""
    admin = _user("req-form", GROUP_ADMIN, superuser=True)
    page = DjClient()
    page.force_login(admin)
    html = page.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode()
    start = html.index('<form id="changelist-form"')
    close = html.index("</form>", start)
    body = html[start:close]
    assert "<form" not in body[body.index(">") + 1 :]
    assert 'name="enabled" form="staffreq-toggle"' in body
    assert 'class="hoocon-staffreq__save" form="staffreq-toggle"' in body
    rest = html[close:]
    toggle_url = reverse("admin:staffrequests_staffrequest_toggle")
    form_at = rest.index('<form id="staffreq-toggle"')
    assert toggle_url in rest[form_at : form_at + 160]


def _h1(html: str) -> str:
    start = html.index("<h1")
    return html[start : html.index("</h1>", start)]


@pytest.mark.django_db
def test_header_has_one_link_back_to_the_queue() -> None:
    """В шапке одна «Техподдержка» на очередь: индекс приложения не требует второго клика."""
    admin = _user("req-crumb", GROUP_ADMIN, superuser=True)
    _enable()
    ticket = StaffRequest.objects.create(
        author=admin,
        kind="bug",
        title="Не открывается фильтр",
        body="После сохранения",
    )
    page = DjClient()
    page.force_login(admin)
    listing = reverse("admin:staffrequests_staffrequest_changelist")
    app_index = reverse("admin:app_list", args=["staffrequests"])
    queue = _h1(page.get(listing).content.decode())
    assert queue.count(f'href="{listing}"') == 1
    assert f'href="{app_index}"' not in queue
    assert "Техподдержка" in queue
    card = _h1(page.get(reverse("admin:staffrequests_staffrequest_change", args=[ticket.pk])).content.decode())
    assert card.count(f'href="{listing}"') == 1
    assert f'href="{app_index}"' not in card
    assert "Не открывается фильтр" in card
    home = page.get(app_index)
    assert home.status_code == 302
    assert home.url == listing
    other = _h1(page.get(reverse("admin:sitesettings_sitesettings_changelist")).content.decode())
    assert f'href="{reverse("admin:app_list", args=["sitesettings"])}"' in other
