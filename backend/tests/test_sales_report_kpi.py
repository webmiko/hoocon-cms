"""РОП report: call quality, first touch, cohort conversion, and one manager card."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client as DjClient
from django.urls import reverse
from django.utils import timezone

from accounts.roles import GROUP_MANAGER
from cabinet.models import Order
from crm.models import Call, CallDirection, CallState, Quote, QuoteStatus
from crm.reports import build_sales_report
from leads.models import Lead

User = get_user_model()
_MOSCOW = ZoneInfo("Europe/Moscow")


def _manager(username: str, first_name: str) -> User:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
        first_name=first_name,
    )
    group, _created = Group.objects.get_or_create(name=GROUP_MANAGER)
    user.groups.add(group)
    return user


def _lead(assignee: User, *, created_at) -> Lead:
    lead = Lead.objects.create(
        name="Клиент",
        email=f"{assignee.username}-{created_at.timestamp()}@example.com",
        message="x" * 20,
        assignee=assignee,
    )
    Lead.objects.filter(pk=lead.pk).update(created_at=created_at)
    lead.refresh_from_db()
    return lead


@pytest.mark.django_db
def test_sales_report_splits_missed_talked_and_unlinked_calls() -> None:
    """Пропущенный — входящий завершённый без разговора; идущий звонок им не считается."""
    anna = _manager("kpi-anna", "Анна")
    boris = _manager("kpi-boris", "Борис")
    now = timezone.now()
    lead = _lead(anna, created_at=now)
    Call.objects.create(
        entry_id="kpi-miss",
        manager=anna,
        direction=CallDirection.INBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=0,
        started_at=now,
    )
    Call.objects.create(
        entry_id="kpi-in",
        manager=anna,
        direction=CallDirection.INBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=40,
        started_at=now,
        lead=lead,
    )
    Call.objects.create(
        entry_id="kpi-out",
        manager=anna,
        direction=CallDirection.OUTBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=10,
        started_at=now,
        lead=lead,
    )
    Call.objects.create(
        entry_id="kpi-live",
        manager=anna,
        direction=CallDirection.INBOUND,
        state=CallState.APPEARED,
        talk_duration=0,
        started_at=now,
    )
    Call.objects.create(
        entry_id="kpi-boris",
        manager=boris,
        direction=CallDirection.INBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=0,
        started_at=now,
    )
    report = build_sales_report(since=now - timedelta(days=7), user=None)
    anna_row = next(row for row in report["managers"] if row["user_id"] == anna.pk)
    boris_row = next(row for row in report["managers"] if row["user_id"] == boris.pk)
    assert anna_row["calls_missed"] == 1
    assert anna_row["calls_unlinked"] == 2
    assert anna_row["calls_inbound_talked"] == 1
    assert anna_row["calls_outbound_talked"] == 1
    assert anna_row["avg_talk_seconds"] == 25
    assert anna_row["avg_talk_label"] == "25 с"
    assert boris_row["calls_missed"] == 1
    assert boris_row["calls_inbound_talked"] == 0
    assert report["totals"]["calls_missed"] == 2


@pytest.mark.django_db
def test_first_touch_is_median_and_ignores_opening_and_early_calls() -> None:
    """Касание — медиана до звонка после создания. Звонок до заявки и автозаметка не считаются."""
    manager = _manager("kpi-touch", "Глеб")
    opened = timezone.now() - timedelta(hours=6)
    first = _lead(manager, created_at=opened)
    second = _lead(manager, created_at=opened)
    _lead(manager, created_at=opened)
    Call.objects.create(
        entry_id="kpi-early",
        manager=manager,
        lead=first,
        direction=CallDirection.OUTBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=5,
        started_at=opened - timedelta(hours=1),
    )
    Call.objects.create(
        entry_id="kpi-hour",
        manager=manager,
        lead=first,
        direction=CallDirection.OUTBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=5,
        started_at=opened + timedelta(minutes=60),
    )
    Call.objects.create(
        entry_id="kpi-three",
        manager=manager,
        lead=second,
        direction=CallDirection.OUTBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=5,
        started_at=opened + timedelta(minutes=180),
    )
    report = build_sales_report(since=opened - timedelta(days=1), user=None)
    row = next(item for item in report["managers"] if item["user_id"] == manager.pk)
    assert row["first_touch_minutes"] == 120
    assert row["first_touch_label"] == "2 ч"
    assert row["leads_untouched"] == 1


@pytest.mark.django_db
def test_cohort_conversion_follows_the_lead_not_the_quote_author() -> None:
    """Доля считается по заявкам периода. КП коллеги по этой заявке всё равно засчитывается."""
    owner = _manager("kpi-owner", "Дана")
    other = _manager("kpi-other", "Егор")
    created = timezone.now() - timedelta(hours=2)
    with_quote = _lead(owner, created_at=created)
    with_order = _lead(owner, created_at=created)
    _lead(owner, created_at=created)
    Quote.objects.create(
        client=with_quote.client,
        lead=with_quote,
        created_by=other,
        status=QuoteStatus.SENT,
        sent_at=timezone.now(),
    )
    accepted = Quote.objects.create(
        client=with_order.client,
        lead=with_order,
        created_by=owner,
        status=QuoteStatus.ACCEPTED,
        sent_at=timezone.now(),
    )
    Order.objects.create(client=with_order.client, quote=accepted, number="З-KPI-1")
    Quote.objects.create(
        client=with_quote.client,
        created_by=owner,
        status=QuoteStatus.SENT,
        sent_at=timezone.now(),
    )
    report = build_sales_report(since=created - timedelta(hours=1), user=None)
    row = next(item for item in report["managers"] if item["user_id"] == owner.pk)
    assert row["cohort_quote_pct"] == 67
    assert row["cohort_quote_label"] == "67%"
    assert row["cohort_order_pct"] == 33
    assert row["cohort_order_label"] == "33%"
    assert other_row_quotes(report, other.pk) == 0


def other_row_quotes(report: dict, user_id: int) -> int:
    row = next(item for item in report["managers"] if item["user_id"] == user_id)
    return int(row["cohort_quote_pct"] or 0)


@pytest.mark.django_db
def test_series_puts_yesterdays_lead_and_miss_on_that_day() -> None:
    """История за 7 дней кладёт заявку и пропущенный в день события, не в соседний."""
    manager = _manager("kpi-series", "Жанна")
    now = timezone.now()
    yesterday = now - timedelta(days=1)
    _lead(manager, created_at=yesterday)
    Call.objects.create(
        entry_id="kpi-series-miss",
        manager=manager,
        direction=CallDirection.INBOUND,
        state=CallState.DISCONNECTED,
        talk_duration=0,
        started_at=yesterday,
    )
    _lead(manager, created_at=now)
    report = build_sales_report(since=now - timedelta(days=7), user=None)
    assert report["series"]["grain"] == "day"
    assert report["series"]["caption"] == "Новые заявки и пропущенные по дням"
    yesterday_local = timezone.localtime(yesterday, _MOSCOW)
    today_local = timezone.localtime(now, _MOSCOW)
    yesterday_label = f"{yesterday_local.day:02d}.{yesterday_local.month:02d}"
    today_label = f"{today_local.day:02d}.{today_local.month:02d}"
    by_label = {bucket["label"]: bucket for bucket in report["series"]["buckets"]}
    assert by_label[yesterday_label]["leads_new"] == 1
    assert by_label[yesterday_label]["calls_missed"] == 1
    assert by_label[today_label]["leads_new"] == 1
    assert by_label[today_label]["calls_missed"] == 0
    week = build_sales_report(since=None, user=None)
    assert week["series"]["grain"] == "week"
    assert len(week["series"]["buckets"]) == 12
    assert sum(bucket["leads_new"] for bucket in week["series"]["buckets"]) == 2


@pytest.mark.django_db
def test_manager_card_is_private_and_the_page_names_the_kpis() -> None:
    """Чужой manager= игнорируется. Админ открывает одну карточку. Страница показывает новые подписи."""
    owner = _manager("kpi-page-a", "Зинаида")
    colleague = _manager("kpi-page-b", "Игорь")
    owner.user_permissions.add(Permission.objects.get(codename="view_client"))
    now = timezone.now()
    Quote.objects.create(client=_lead(owner, created_at=now).client, created_by=owner)
    Quote.objects.create(client=_lead(colleague, created_at=now).client, created_by=colleague)
    scoped = build_sales_report(since=None, user=owner, manager_id=colleague.pk)
    assert [row["user_id"] for row in scoped["managers"]] == [owner.pk]
    assert scoped["focus"] is None
    admin = User.objects.create_superuser(
        username="kpi-rop",
        email="kpi-rop@example.com",
        password="password12",
    )
    focused = build_sales_report(since=None, user=admin, manager_id=colleague.pk)
    assert focused["focus"]["display_name"]
    assert [row["user_id"] for row in focused["managers"]] == [colleague.pk]
    page = DjClient()
    page.force_login(admin)
    url = reverse("admin:crm_client_sales_report")
    department = page.get(url)
    body = department.content.decode()
    assert department.status_code == 200
    assert "Пропущенные" in body
    assert "Первое касание" in body
    assert "Новые заявки и пропущенные по дням" in body
    assert f"manager={colleague.pk}" in body
    card = page.get(f"{url}?manager={colleague.pk}")
    card_body = card.content.decode()
    assert "Игорь" in card_body
    assert "Зинаида" not in card_body
    assert "Все менеджеры" in card_body
    page.force_login(owner)
    own = page.get(f"{url}?manager={colleague.pk}")
    own_body = own.content.decode()
    assert "Зинаида" in own_body
    assert "Игорь" not in own_body
    assert "Показаны только ваши цифры" in own_body
