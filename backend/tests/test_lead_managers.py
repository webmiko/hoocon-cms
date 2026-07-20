"""Tests for lead manager assignment and processing statistics."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from leads.models import Lead
from leads.services import (
    apply_lead_manager_on_save,
    build_lead_processing_stats,
    take_lead_in_work,
)

User = get_user_model()


@pytest.mark.django_db
def test_take_lead_in_work_sets_assignee_and_status() -> None:
    """Manager takes a lead: assignee + in_progress."""
    manager = User.objects.create_user(
        username="mgr1",
        email="mgr1@example.com",
        password="password12",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Client",
        email="client@example.com",
        message="Нужна консультация по приводам.",
        status=Lead.LeadStatus.NEW,
    )
    take_lead_in_work(lead, manager)
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    assert lead.assignee_id == manager.pk


@pytest.mark.django_db
def test_apply_lead_manager_on_save_sets_processed_by_when_done() -> None:
    """Completing a lead stamps processed_by / processed_at."""
    manager = User.objects.create_user(
        username="mgr2",
        email="mgr2@example.com",
        password="password12",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Done Client",
        email="done@example.com",
        message="Заявка будет завершена.",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=manager,
    )
    lead.status = Lead.LeadStatus.DONE
    apply_lead_manager_on_save(lead, actor=manager)
    assert lead.processed_by_id == manager.pk
    assert lead.processed_at is not None
    assert lead.assignee_id == manager.pk


@pytest.mark.django_db
def test_build_lead_processing_stats_by_manager() -> None:
    """Stats aggregate totals and per-manager done / open counts."""
    mgr_a = User.objects.create_user(
        username="stats_a",
        email="a@example.com",
        password="password12",
        is_staff=True,
        first_name="Анна",
    )
    mgr_b = User.objects.create_user(
        username="stats_b",
        email="b@example.com",
        password="password12",
        is_staff=True,
        first_name="Борис",
    )
    now = timezone.now()
    open_a = Lead.objects.create(
        name="Open A",
        email="oa@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr_a,
    )
    done_a = Lead.objects.create(
        name="Done A",
        email="da@example.com",
        message="y" * 20,
        status=Lead.LeadStatus.DONE,
        assignee=mgr_a,
        processed_by=mgr_a,
    )
    Lead.objects.filter(pk=done_a.pk).update(
        created_at=now - timedelta(hours=5),
        processed_at=now - timedelta(hours=2),
    )
    done_b = Lead.objects.create(
        name="Done B",
        email="db@example.com",
        message="z" * 20,
        status=Lead.LeadStatus.DONE,
        assignee=mgr_b,
        processed_by=mgr_b,
    )
    Lead.objects.filter(pk=done_b.pk).update(
        created_at=now - timedelta(days=3),
        processed_at=now - timedelta(days=2),
    )
    Lead.objects.create(
        name="New free",
        email="new@example.com",
        message="w" * 20,
        status=Lead.LeadStatus.NEW,
    )
    assert open_a.pk

    stats = build_lead_processing_stats(since=now - timedelta(days=7))
    assert stats["totals"]["new"] == 1
    assert stats["totals"]["in_progress"] == 1
    assert stats["totals"]["done"] == 2
    assert stats["totals"]["done_in_period"] == 2

    by_id = {row["user_id"]: row for row in stats["managers"]}
    assert by_id[mgr_a.pk]["in_progress"] == 1
    assert by_id[mgr_a.pk]["done_in_period"] == 1
    assert by_id[mgr_b.pk]["done_in_period"] == 1
    assert by_id[mgr_a.pk]["avg_hours_to_done"] is not None


@pytest.mark.django_db
def test_admin_lead_form_shows_manager_fields() -> None:
    """Change form includes assignee / processed_by fields."""
    admin_user = User.objects.create_superuser(
        username="lead-mgr-admin",
        email="lead-mgr-admin@example.com",
        password="password12",
    )
    lead = Lead.objects.create(
        name="Form Lead",
        email="form@example.com",
        message="Проверка полей менеджера.",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get(f"/admin/leads/lead/{lead.pk}/change/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "assignee" in html
    assert 'name="assignee"' in html or "id_assignee" in html
    assert "processed_by" in html or "id_processed_by" in html
    assert "Менеджер" in html


@pytest.mark.django_db
def test_admin_stats_page_requires_staff_and_shows_totals() -> None:
    """Stats page is staff-only and renders processing totals."""
    Lead.objects.create(
        name="Stat Lead",
        email="stat@example.com",
        message="Для страницы статистики.",
        status=Lead.LeadStatus.NEW,
    )
    anon = Client()
    assert anon.get("/admin/leads/lead/stats/").status_code in {302, 403}

    admin_user = User.objects.create_superuser(
        username="stats-admin",
        email="stats-admin@example.com",
        password="password12",
    )
    client = Client()
    client.force_login(admin_user)
    response = client.get("/admin/leads/lead/stats/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "Статистика заявок" in html
    assert "Новые" in html or "new" in html.lower()
    assert "Менеджер" in html or "менеджер" in html


@pytest.mark.django_db
def test_admin_action_take_in_work() -> None:
    """Changelist action assigns selected leads to current manager."""
    manager = User.objects.create_superuser(
        username="take-mgr",
        email="take-mgr@example.com",
        password="password12",
    )
    lead = Lead.objects.create(
        name="Take Me",
        email="take@example.com",
        message="Взять в работу через action.",
        status=Lead.LeadStatus.NEW,
    )
    client = Client()
    client.force_login(manager)
    response = client.post(
        "/admin/leads/lead/",
        {
            "action": "action_take_in_work",
            "_selected_action": [str(lead.pk)],
        },
    )
    assert response.status_code in {200, 302}
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.IN_PROGRESS
    assert lead.assignee_id == manager.pk
