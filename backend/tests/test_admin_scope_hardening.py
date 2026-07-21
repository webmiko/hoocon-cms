"""Regression tests for Admin CRM/leads permission and scope hardening."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

from crm.models import Activity, ActivityType
from crm.models import Client as CrmClient
from leads.models import Lead

User = get_user_model()


def _staff_with_perms(*, username: str, codenames: tuple[str, ...]) -> User:
    """Create staff user with given model permissions."""
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.mark.django_db
def test_staff_without_lead_perm_cannot_open_stats() -> None:
    """Any staff without leads.view_lead gets 403 on stats."""
    staff = _staff_with_perms(username="no-lead-stats", codenames=())
    client = Client()
    client.force_login(staff)
    response = client.get(reverse("admin:leads_lead_stats"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_without_lead_perm_cannot_poll_new_count() -> None:
    """Sticker JSON requires leads.view_lead."""
    staff = _staff_with_perms(username="no-lead-count", codenames=())
    client = Client()
    client.force_login(staff)
    response = client.get(reverse("admin:leads_lead_new_count"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_without_change_client_cannot_compose_email() -> None:
    """Compose-email requires change_client (not bare is_staff)."""
    staff = _staff_with_perms(
        username="view-only-crm",
        codenames=("view_client",),
    )
    crm = CrmClient.objects.create(name="Buyer", email="buyer-perm@example.com")
    client = Client()
    client.force_login(staff)
    url = reverse("admin:crm_client_compose_email", args=[crm.pk])
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_manager_cannot_open_foreign_client_card() -> None:
    """Client changelist/change are scoped — foreign cards are 404."""
    mgr = _staff_with_perms(
        username="crm-scope-mgr",
        codenames=("view_client", "change_client"),
    )
    other = User.objects.create_user(
        username="crm-scope-other",
        email="crm-scope-other@example.com",
        password="password12",
        is_staff=True,
    )
    foreign = CrmClient.objects.create(
        name="Foreign Co",
        email="foreign-card@example.com",
        assignee=other,
    )
    Lead.objects.create(
        name="Foreign Lead",
        email="foreign-card@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
        client=foreign,
    )
    client = Client()
    client.force_login(mgr)
    response = client.get(reverse("admin:crm_client_change", args=[foreign.pk]))
    # Django Admin redirects missing/out-of-scope objects to the index (302).
    assert response.status_code in (302, 403, 404)
    if response.status_code == 302:
        assert response.url.startswith("/admin/")
    list_html = client.get(reverse("admin:crm_client_changelist")).content.decode()
    assert "foreign-card@example.com" not in list_html


@pytest.mark.django_db
def test_activity_author_does_not_unlock_foreign_lead() -> None:
    """Creating an activity on a foreign lead must not add it to lead scope."""
    from leads.services import scope_leads_for_manager

    mgr = _staff_with_perms(
        username="act-escalation",
        codenames=("view_lead", "view_client", "add_activity", "change_activity"),
    )
    other = User.objects.create_user(
        username="act-other",
        email="act-other@example.com",
        password="password12",
        is_staff=True,
    )
    foreign_client = CrmClient.objects.create(
        name="Other Client",
        email="act-foreign@example.com",
        assignee=other,
    )
    foreign_lead = Lead.objects.create(
        name="Secret",
        email="act-foreign@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
        client=foreign_client,
    )
    Activity.objects.create(
        client=foreign_client,
        lead=foreign_lead,
        activity_type=ActivityType.NOTE,
        subject="Hack attempt",
        author=mgr,
    )
    visible = set(
        scope_leads_for_manager(Lead.objects.all(), mgr).values_list("pk", flat=True),
    )
    assert foreign_lead.pk not in visible


@pytest.mark.django_db
def test_dashboard_kpi_in_progress_scoped_for_manager() -> None:
    """Manager dashboard «В работе» does not include other managers' leads."""
    from django.test import RequestFactory

    from config.dashboard import build_admin_dashboard

    mgr = _staff_with_perms(
        username="dash-scope",
        codenames=("view_lead", "view_client"),
    )
    other = User.objects.create_user(
        username="dash-other",
        email="dash-other@example.com",
        password="password12",
        is_staff=True,
    )
    Lead.objects.create(
        name="Mine open",
        email="mine-open@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr,
    )
    Lead.objects.create(
        name="Theirs open",
        email="theirs-open@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
    )
    request = RequestFactory().get("/admin/")
    request.user = mgr
    dash = build_admin_dashboard(request)["hoocon_dashboard"]
    in_progress_card = next(c for c in dash["cards"] if c["label"] == "В работе")
    assert in_progress_card["value"] == 1


@pytest.mark.django_db
def test_take_in_work_admin_action_reports_skipped() -> None:
    """Changelist action counts only successful takes."""
    from django.contrib.admin.sites import site
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore
    from django.test import RequestFactory

    from leads.admin import LeadAdmin

    mgr_a = _staff_with_perms(
        username="take-a",
        codenames=("view_lead", "change_lead"),
    )
    mgr_b = User.objects.create_user(
        username="take-b",
        email="take-b@example.com",
        password="password12",
        is_staff=True,
    )
    free = Lead.objects.create(
        name="Free2",
        email="free2-take@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    owned = Lead.objects.create(
        name="Owned",
        email="owned-take@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=mgr_b,
    )
    admin = LeadAdmin(Lead, site)
    request = RequestFactory().post("/admin/leads/lead/")
    request.user = mgr_a
    request.session = SessionStore()
    request._messages = FallbackStorage(request)  # noqa: SLF001

    admin.action_take_in_work(request, Lead.objects.filter(pk__in=[free.pk, owned.pk]))
    text = " ".join(str(m) for m in request._messages)  # noqa: SLF001
    assert "Взято в работу: 1" in text
    assert "Пропущено" in text
    free.refresh_from_db()
    owned.refresh_from_db()
    assert free.assignee_id == mgr_a.pk
    assert owned.assignee_id == mgr_b.pk
