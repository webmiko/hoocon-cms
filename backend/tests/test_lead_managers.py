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
    _lead, taken = take_lead_in_work(lead, manager)
    assert taken is True
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
def test_scope_leads_for_manager_sees_new_own_and_client() -> None:
    """Manager list: new + assignee/processed + client assignee (not activity)."""
    from crm.models import Activity, ActivityType
    from crm.models import Client as CrmClient
    from leads.services import scope_leads_for_manager

    mgr = User.objects.create_user(
        username="scope-mgr",
        email="scope-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    other = User.objects.create_user(
        username="scope-other",
        email="scope-other@example.com",
        password="password12",
        is_staff=True,
    )
    new_lead = Lead.objects.create(
        name="New",
        email="new@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    mine = Lead.objects.create(
        name="Mine",
        email="mine@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr,
    )
    finished = Lead.objects.create(
        name="Done by me",
        email="done@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.DONE,
        processed_by=mgr,
    )
    crm = CrmClient.objects.create(
        name="Card",
        email="card-scope@example.com",
        assignee=mgr,
    )
    on_my_client = Lead.objects.create(
        name="Client lead",
        email="card-scope@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
        client=crm,
    )
    mentioned = Lead.objects.create(
        name="Mentioned",
        email="mention@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
    )
    Activity.objects.create(
        client=crm,
        lead=mentioned,
        activity_type=ActivityType.NOTE,
        subject="Упоминание менеджера",
        author=mgr,
    )
    foreign = Lead.objects.create(
        name="Foreign",
        email="foreign@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
    )

    visible = set(
        scope_leads_for_manager(Lead.objects.all(), mgr).values_list("pk", flat=True),
    )
    assert new_lead.pk in visible
    assert mine.pk in visible
    assert finished.pk in visible
    assert on_my_client.pk in visible
    # Activity author must NOT unlock a foreign lead (IDOR).
    assert mentioned.pk not in visible
    assert foreign.pk not in visible

    # Superuser sees everything.
    su = User.objects.create_superuser(
        username="scope-su",
        email="scope-su@example.com",
        password="password12",
    )
    assert scope_leads_for_manager(Lead.objects.all(), su).count() == Lead.objects.count()


@pytest.mark.django_db
def test_manager_admin_changelist_hides_foreign_leads() -> None:
    """Non-superuser staff changelist does not list another manager's lead."""
    mgr = User.objects.create_user(
        username="list-mgr",
        email="list-mgr@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    # Grant admin access to Lead.
    from django.contrib.auth.models import Permission

    for codename in ("view_lead", "change_lead"):
        mgr.user_permissions.add(Permission.objects.get(codename=codename))

    other = User.objects.create_user(
        username="list-other",
        email="list-other@example.com",
        password="password12",
        is_staff=True,
    )
    Lead.objects.create(
        name="Visible new",
        email="vis-new@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    Lead.objects.create(
        name="Hidden",
        email="hidden@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
    )
    client = Client()
    client.force_login(mgr)
    html = client.get("/admin/leads/lead/").content.decode()
    assert "Visible new" in html
    assert "Hidden" not in html


@pytest.mark.django_db
def test_admin_lead_form_shows_manager_fields() -> None:
    """View mode is read-only; edit mode exposes assignee / processed_by."""
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

    view = client.get(f"/admin/leads/lead/{lead.pk}/change/")
    assert view.status_code == 200
    view_html = view.content.decode()
    assert "Редактировать" in view_html
    assert "Менеджер" in view_html
    # View mode: no editable select for assignee.
    assert 'name="assignee"' not in view_html

    edit = client.get(f"/admin/leads/lead/{lead.pk}/change/?edit=1")
    assert edit.status_code == 200
    edit_html = edit.content.decode()
    assert 'name="assignee"' in edit_html or "id_assignee" in edit_html
    assert "processed_by" in edit_html or "id_processed_by" in edit_html
    assert "К просмотру" in edit_html


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


@pytest.mark.django_db
def test_take_lead_in_work_skips_other_assignee() -> None:
    """Second manager cannot steal a lead already assigned."""
    mgr_a = User.objects.create_user(
        username="lock_a",
        email="lock_a@example.com",
        password="password12",
        is_staff=True,
    )
    mgr_b = User.objects.create_user(
        username="lock_b",
        email="lock_b@example.com",
        password="password12",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Locked",
        email="locked@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    _lead, taken_a = take_lead_in_work(lead, mgr_a)
    assert taken_a is True
    _lead, taken_b = take_lead_in_work(lead, mgr_b)
    assert taken_b is False
    lead.refresh_from_db()
    assert lead.assignee_id == mgr_a.pk


@pytest.mark.django_db
def test_reopen_done_clears_processed_fields() -> None:
    """Leaving DONE clears processed_by / processed_at for accurate stats."""
    manager = User.objects.create_user(
        username="reopen",
        email="reopen@example.com",
        password="password12",
        is_staff=True,
    )
    lead = Lead.objects.create(
        name="Reopen",
        email="reopen-lead@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.DONE,
        assignee=manager,
        processed_by=manager,
        processed_at=timezone.now(),
    )
    lead.status = Lead.LeadStatus.IN_PROGRESS
    apply_lead_manager_on_save(lead, actor=manager)
    assert lead.processed_by_id is None
    assert lead.processed_at is None


@pytest.mark.django_db
def test_done_total_ignores_processed_by_on_reopened() -> None:
    """done_total counts only status=DONE, not stale processed_by."""
    manager = User.objects.create_user(
        username="stats_reopen",
        email="stats_reopen@example.com",
        password="password12",
        is_staff=True,
    )
    # Still DONE — counts.
    Lead.objects.create(
        name="Still done",
        email="stilldone@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.DONE,
        processed_by=manager,
        processed_at=timezone.now(),
    )
    # Reopened but processed_by still set in DB (legacy) — must not count.
    Lead.objects.create(
        name="Reopened",
        email="reopened@example.com",
        message="y" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=manager,
        processed_by=manager,
        processed_at=timezone.now(),
    )
    stats = build_lead_processing_stats()
    by_id = {row["user_id"]: row for row in stats["managers"]}
    assert by_id[manager.pk]["done_total"] == 1


@pytest.mark.django_db
def test_admin_mark_done_creates_activity() -> None:
    """Mark-done action writes CRM Activity when lead has a client."""
    from crm.models import Activity, ActivityType

    manager = User.objects.create_superuser(
        username="mark-done-mgr",
        email="mark-done@example.com",
        password="password12",
    )
    lead = Lead.objects.create(
        name="Mark Done",
        email="markdone@example.com",
        message="Завершить через action.",
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=manager,
    )
    lead.refresh_from_db()
    assert lead.client_id is not None
    client = Client()
    client.force_login(manager)
    response = client.post(
        "/admin/leads/lead/",
        {
            "action": "action_mark_done",
            "_selected_action": [str(lead.pk)],
        },
    )
    assert response.status_code in {200, 302}
    lead.refresh_from_db()
    assert lead.status == Lead.LeadStatus.DONE
    assert Activity.objects.filter(
        lead=lead,
        activity_type=ActivityType.STATUS,
    ).exists()
