"""Tests for Admin home dashboard (stats, feeds, notifications)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from leads.models import Lead

User = get_user_model()


@pytest.mark.django_db
def test_admin_index_shows_dashboard_for_superuser() -> None:
    """Home page renders dashboard cards, alerts, and feeds."""
    admin_user = User.objects.create_superuser(
        username="dash-admin",
        email="dash-admin@example.com",
        password="password12",
    )
    Lead.objects.create(
        name="Dash Lead",
        email="dash-lead@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-dash" in html or "Панель управления" in html
    assert "Оповещения" in html
    assert "Лиды по статусам" in html
    assert "Последние заявки" in html
    assert "Dash Lead" in html
    assert "Изменения в админке" in html


@pytest.mark.django_db
def test_admin_index_has_no_quick_links_strip() -> None:
    """Quick-links strip removed; lead stats live in the sections menu."""
    admin_user = User.objects.create_superuser(
        username="dash-quick",
        email="dash-quick@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "hoocon-dash__quick" not in html
    assert "/admin/leads/lead/stats/" in html


@pytest.mark.django_db
def test_build_admin_dashboard_payload_keys() -> None:
    """Service returns expected dashboard sections for staff."""
    from django.test import RequestFactory

    from config.dashboard import build_admin_dashboard

    user = User.objects.create_superuser(
        username="dash-svc",
        email="dash-svc@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = user
    payload = build_admin_dashboard(request)
    dash = payload["hoocon_dashboard"]
    assert "notifications" in dash
    assert "cards" in dash
    assert "chart" in dash
    assert "recent_leads" in dash
    assert "admin_log" in dash
    assert dash["period_days"] == 30
    assert dash["today"]["empty"] is True


def _touch(company, when, *, assignee=None, key: str, phone: str = "+7 (843) 554-00-45"):
    from crm.models import PlannedTouch

    if phone and company.phone != phone:
        company.phone = phone
        company.save(update_fields=["phone"])
    return PlannedTouch.objects.create(
        company=company,
        assignee=assignee,
        starts_at=when,
        title=f"Звонок: {company.name}",
        dedupe_key=key,
    )


def _staff(username: str, *codenames: str):
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="x",
        is_staff=True,
    )
    for code in codenames:
        perm = Permission.objects.get(content_type__app_label="crm", codename=code)
        user.user_permissions.add(perm)
    return user


@pytest.mark.django_db
def test_today_board_groups_unassigned_then_overdue_then_later() -> None:
    """A free call offers «Взять». Another manager's call is not on this board."""
    from datetime import datetime, timedelta

    from django.contrib.auth.models import Group
    from django.test import RequestFactory
    from django.utils import timezone

    from accounts.roles import GROUP_ADMIN
    from config.dashboard import build_admin_dashboard
    from crm.models import Company

    now = timezone.now()
    day_end = timezone.make_aware(
        datetime.combine(timezone.localdate(), datetime.min.time()),
    ) + timedelta(days=1)
    later = now + timedelta(minutes=30)
    if later >= day_end:
        later = day_end - timedelta(seconds=1)
    me = _staff("today-me", "view_plannedtouch", "change_plannedtouch")
    other = _staff("today-other", "view_plannedtouch", "change_plannedtouch")
    other.first_name = "Ольга"
    other.last_name = "Смирнова"
    other.save(update_fields=["first_name", "last_name"])
    free = Company.objects.create(name="Свободная")
    mine_late = Company.objects.create(name="Моя позже")
    mine_old = Company.objects.create(name="Моя вчера")
    theirs = Company.objects.create(name="Чужая", assignee=other)
    _touch(free, now - timedelta(hours=3), key="free")
    _touch(mine_late, later, assignee=me, key="later")
    _touch(mine_old, now - timedelta(days=1), assignee=me, key="old")
    _touch(theirs, now - timedelta(hours=1), key="theirs")
    tomorrow_company = Company.objects.create(name="Завтра")
    _touch(tomorrow_company, day_end + timedelta(hours=2), key="tomorrow")

    request = RequestFactory().get("/admin/")
    request.user = me
    groups = {group["key"]: group for group in build_admin_dashboard(request)["hoocon_dashboard"]["today"]["groups"]}
    free_row = groups["unassigned"]["items"][0]
    assert free_row["name"] == "Свободная"
    assert free_row["tel"] == "+78435540045"
    assert free_row["assign_url"]
    assert free_row["owner"] == ""
    assert [item["name"] for item in groups["overdue"]["items"]] == ["Моя вчера"]
    assert "Чужая" not in str(groups)
    assert "Ольга Смирнова" not in str(groups)
    assert [item["name"] for item in groups["later"]["items"]] == ["Моя позже"]
    assert "Завтра" not in str(groups)

    head = _staff("today-head", "view_plannedtouch")
    head.groups.add(Group.objects.get(name=GROUP_ADMIN))
    request.user = head
    head_groups = {
        group["key"]: group for group in build_admin_dashboard(request)["hoocon_dashboard"]["today"]["groups"]
    }
    head_overdue = {item["name"]: item for item in head_groups["overdue"]["items"]}
    assert head_overdue["Чужая"]["owner"] == "Ольга Смирнова"
    assert head_overdue["Чужая"]["assign_url"] == ""


@pytest.mark.django_db
def test_today_list_sits_above_sections_and_assign_claims_the_call() -> None:
    """Home shows «Сегодня» before «Разделы». POST assigns; GET and a foreign call do not."""
    from datetime import timedelta

    from django.utils import timezone

    from crm.models import Company

    now = timezone.now()
    org = Company.objects.create(name="Панель Телефон", phone="+7 (843) 555-53-96")
    touch = _touch(org, now - timedelta(hours=1), key="panel", phone="")
    admin_user = User.objects.create_superuser("today-home", "today-home@example.com", "password12")
    client = Client()
    client.force_login(admin_user)
    page = client.get(reverse("admin:index"))
    html = page.content.decode()
    board = html.split('aria-label="Дашборд"', 1)[1]
    assert board.index("Сегодня") < board.index("Разделы")
    assert "Панель Телефон" in html
    assert 'href="tel:+78435555396"' in html
    today_html = board.split("Разделы", 1)[0]
    assert "Взять" in today_html
    assert "Назначить меня" not in today_html
    css = open("static/admin/css/hoocon-os27.css", encoding="utf-8").read()
    item_rule = css.split(".hoocon-today__item {", 1)[1].split("}", 1)[0]
    assert "display: flex" in item_rule
    assert "flex-wrap: wrap" in item_rule

    from io import StringIO

    from django.core.management import call_command

    from content.models import WikiDocument

    call_command("seed_wiki", stdout=StringIO())
    guide = WikiDocument.objects.get(slug="admin-3-0-manager-guide").body
    assert guide.index("changelog-company-list-view") < guide.index("changelog-company-owner-field")
    assert guide.index("changelog-company-owner-field") < guide.index("changelog-own-cards")
    assert guide.index("changelog-own-cards") < guide.index("changelog-page-memos")
    assert guide.index("changelog-planned-touch-status") < guide.index("changelog-today-board")
    assert guide.index("changelog-today-board") < guide.index("changelog-company-phones")
    assert "Взять" in guide

    denied = client.get(reverse("admin:crm_plannedtouch_assign_me", args=[touch.pk]))
    assert denied.status_code == 405
    touch.refresh_from_db()
    assert touch.assignee_id is None

    taken = client.post(reverse("admin:crm_plannedtouch_assign_me", args=[touch.pk]))
    assert taken.status_code == 302
    touch.refresh_from_db()
    org.refresh_from_db()
    assert touch.assignee_id == admin_user.pk
    assert org.assignee_id == admin_user.pk

    stranger = _staff("today-stranger", "view_plannedtouch", "change_plannedtouch")
    other = Client()
    other.force_login(stranger)
    blocked = other.post(reverse("admin:crm_plannedtouch_assign_me", args=[touch.pk]))
    assert blocked.status_code == 403
    touch.refresh_from_db()
    assert touch.assignee_id == admin_user.pk


@pytest.mark.django_db
def test_today_ninth_unassigned_call_is_counted_not_listed() -> None:
    """The home list stays short: eight cards and a remainder."""
    from datetime import timedelta

    from django.test import RequestFactory
    from django.utils import timezone

    from config.dashboard import build_admin_dashboard
    from crm.models import Company

    now = timezone.now()
    user = _staff("today-cap", "view_plannedtouch")
    for index in range(9):
        org = Company.objects.create(name=f"Компания {index}")
        _touch(org, now - timedelta(minutes=index + 1), key=f"cap-{index}", phone="")
    request = RequestFactory().get("/admin/")
    request.user = user
    group = build_admin_dashboard(request)["hoocon_dashboard"]["today"]["groups"][0]
    assert group["key"] == "unassigned"
    assert len(group["items"]) == 8
    assert group["more"] == 1
    assert group["items"][0]["assign_url"] == ""
