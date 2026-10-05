"""SLA первого ответа на заявку — рабочие часы supportchat-расписания.

Инвариант: сайт обещает ответ «в течение 2 рабочих часов»
(``leads.services._CLIENT_RESPONSE_TIME``), поэтому дедлайн идёт по
рабочим интервалам, а не по календарным часам.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.test import Client as HttpClient
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from leads.models import Lead
from leads.sla import lead_response_deadline, overdue_new_leads
from supportchat.schedule import ensure_default_schedule

_MSK = ZoneInfo("Europe/Moscow")


def _dt(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Aware Europe/Moscow datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=_MSK)


@pytest.fixture
def schedule(db) -> None:
    """Ensure the default Mon–Fri 9–18 (Fri till 17:00) schedule exists."""
    ensure_default_schedule()


def _lead_at(created_at: datetime, *, email: str) -> Lead:
    """Create a NEW lead backdated to ``created_at``."""
    lead = Lead.objects.create(name="SLA Тест", email=email, message="x" * 20)
    Lead.objects.filter(pk=lead.pk).update(created_at=created_at)
    lead.refresh_from_db()
    return lead


@pytest.mark.django_db
def test_deadline_same_workday(schedule) -> None:
    """Created Mon 10:00 → deadline Mon 12:00 (ровно 2 рабочих часа)."""
    assert lead_response_deadline(_dt(2026, 10, 5, 10)) == _dt(2026, 10, 5, 12)


@pytest.mark.django_db
def test_deadline_spans_weekend(schedule) -> None:
    """Fri 16:30 (день до 17:00) → 30 мин Пт + 90 мин Пн → Пн 10:30."""
    assert lead_response_deadline(_dt(2026, 10, 9, 16, 30)) == _dt(2026, 10, 12, 10, 30)


@pytest.mark.django_db
def test_deadline_created_on_weekend(schedule) -> None:
    """Субботняя заявка начинает гореть Пн 9:00 → дедлайн Пн 11:00."""
    assert lead_response_deadline(_dt(2026, 10, 10, 9)) == _dt(2026, 10, 12, 11)


@pytest.mark.django_db
def test_deadline_after_hours_rolls_to_next_day(schedule) -> None:
    """Created Mon 20:00 → Tue 9:00 + 2h → Tue 11:00."""
    assert lead_response_deadline(_dt(2026, 10, 5, 20)) == _dt(2026, 10, 6, 11)


@pytest.mark.django_db
def test_overdue_new_leads_flags_expired_only(schedule) -> None:
    """Просрочены только NEW с вышедшим дедлайном; свежие и DONE — нет."""
    old = _lead_at(_dt(2026, 10, 5, 9), email="old-sla@example.com")
    fresh = _lead_at(_dt(2026, 10, 7, 9), email="fresh-sla@example.com")
    done = _lead_at(_dt(2026, 10, 1, 9), email="done-sla@example.com")
    Lead.objects.filter(pk=done.pk).update(status=Lead.LeadStatus.DONE)

    overdue = overdue_new_leads(Lead.objects.all(), now=_dt(2026, 10, 7, 10))
    ids = {lead.pk for lead in overdue}
    assert old.pk in ids
    assert fresh.pk not in ids  # дедлайн Wed 11:00, now Wed 10:00
    assert done.pk not in ids


@pytest.mark.django_db
def test_dashboard_flags_overdue_lead(schedule, django_user_model) -> None:
    """Dashboard notification + card expose SLA-overdue new leads."""
    from config.dashboard import build_admin_dashboard

    _lead_at(_dt(2026, 9, 28, 9), email="overdue-dash@example.com")
    user = django_user_model.objects.create_superuser(
        username="sla-dash",
        email="sla-dash@example.com",
        password="password12",
    )
    request = RequestFactory().get("/admin/")
    request.user = user
    dash = build_admin_dashboard(request)["hoocon_dashboard"]
    titles = [item["title"] for item in dash["notifications"]]
    assert any("Просрочен первый ответ" in title for title in titles)
    card = next(c for c in dash["cards"] if c["label"] == "Просрочено SLA")
    assert card["value"] >= 1


@pytest.mark.django_db
def test_changelist_sla_filter_shows_only_overdue(schedule, django_user_model) -> None:
    """?sla_overdue=yes keeps only past-deadline new leads."""
    _lead_at(_dt(2026, 9, 28, 9), email="overdue-list@example.com")
    _lead_at(timezone.now(), email="fresh-list@example.com")
    user = django_user_model.objects.create_superuser(
        username="sla-list",
        email="sla-list@example.com",
        password="password12",
    )
    http = HttpClient()
    http.force_login(user)
    url = reverse("admin:leads_lead_changelist")
    response = http.get(url + "?status__exact=new&sla_overdue=yes")
    assert response.status_code == 200
    html = response.content.decode()
    assert "overdue-list@example.com" in html
    assert "fresh-list@example.com" not in html
