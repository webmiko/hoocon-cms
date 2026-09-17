"""Tests for lead round-robin routing and notify recipients."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import override_settings

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from leads.models import Lead
from leads.services import (
    assign_lead_on_create,
    assign_lead_round_robin,
    is_aterna_company,
    lookup_aterna_assignee,
    manager_rotation_queryset,
    resolve_lead_notify_recipients,
    scope_leads_for_manager,
)
from leads.tasks import send_lead_notification
from sitesettings.models import SiteSettings

User = get_user_model()


def _make_manager(*, username: str, email: str) -> object:
    """Create staff user in group «Менеджер» with login email."""
    ensure_staff_groups()
    user = User.objects.create_user(
        username=username,
        email=email,
        password="password12",
        is_staff=True,
        is_active=True,
    )
    user.groups.add(Group.objects.get(name=GROUP_MANAGER))
    return user


def _set_mode(mode: str) -> SiteSettings:
    """Ensure singleton and set lead_routing_mode."""
    site = SiteSettings.load()
    site.lead_routing_mode = mode
    site.lead_rr_last_user = None
    site.save(update_fields=["lead_routing_mode", "lead_rr_last_user", "updated_at"])
    return site


@pytest.mark.django_db
def test_is_aterna_company_matches_common_spellings() -> None:
    """ООО Атерна is recognized with optional quotes and spacing."""
    assert is_aterna_company("ООО Атерна")
    assert is_aterna_company("  ооо   «Атерна»  ")
    assert is_aterna_company("Атерна")
    assert not is_aterna_company("ООО Не Атерна")
    assert not is_aterna_company("ООО RoundRobin")


@pytest.mark.django_db
def test_aterna_lead_assigns_assistant_even_when_routing_off() -> None:
    """Aterna leads always go to assistant@hoocon.ru, even with routing off."""
    _make_manager(username="rr-off-other", email="other-mgr@hoocon.ru")
    lyudmila = User.objects.create_user(
        username="assistant",
        email="assistant@hoocon.ru",
        password="password12",
        first_name="Людмила",
        is_staff=True,
        is_active=True,
    )
    _set_mode(SiteSettings.LeadRoutingMode.OFF)
    lead = Lead.objects.create(
        name="Атерна",
        email="aterna@example.com",
        company="ООО Атерна",
        message="x" * 20,
    )
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == lyudmila.pk
    lead.refresh_from_db()
    assert lead.assignee_id == lyudmila.pk
    assert lookup_aterna_assignee().pk == lyudmila.pk


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_aterna_notify_uses_assignee_email_when_routing_off() -> None:
    """Aterna notification goes to assistant@ even when RR mode is off."""
    User.objects.create_user(
        username="assistant-notify",
        email="assistant@hoocon.ru",
        password="password12",
        is_staff=True,
        is_active=True,
    )
    _set_mode(SiteSettings.LeadRoutingMode.OFF)
    lead = Lead.objects.create(
        name="Notify",
        email="notify-aterna@example.com",
        company="ООО «Атерна»",
        message="x" * 20,
    )
    assign_lead_on_create(lead)
    lead.refresh_from_db()
    assert resolve_lead_notify_recipients(lead) == ["assistant@hoocon.ru"]


@pytest.mark.django_db
def test_aterna_skips_round_robin_among_managers() -> None:
    """Aterna company bypasses rotation and keeps RR cursor unchanged."""
    a = _make_manager(username="rr-aterna-a", email="a-aterna@hoocon.ru")
    _make_manager(username="rr-aterna-b", email="b-aterna@hoocon.ru")
    lyudmila = User.objects.create_user(
        username="assistant-rr",
        email="assistant@hoocon.ru",
        password="password12",
        is_staff=True,
        is_active=True,
    )
    site = _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    site.lead_rr_last_user = a
    site.save(update_fields=["lead_rr_last_user", "updated_at"])

    lead = Lead.objects.create(
        name="Aterna RR",
        email="aterna-rr@example.com",
        company="ООО Атерна",
        message="x" * 20,
    )
    picked = assign_lead_on_create(lead)
    assert picked.pk == lyudmila.pk
    site.refresh_from_db()
    assert site.lead_rr_last_user_id == a.pk


@pytest.mark.django_db(transaction=True)
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_api_aterna_assigns_assistant(client) -> None:
    """POST /api/leads/ from ООО Атерна sets assignee assistant@hoocon.ru."""
    from unittest.mock import patch

    _make_manager(username="api-aterna-mgr", email="api-mgr@hoocon.ru")
    lyudmila = User.objects.create_user(
        username="api-assistant",
        email="assistant@hoocon.ru",
        password="password12",
        is_staff=True,
        is_active=True,
    )
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    payload = {
        "name": "API Aterna",
        "email": "api-aterna-client@example.com",
        "company": "ООО Атерна",
        "message": "Заявка от Атерны через API.",
    }
    with patch("leads.views.send_lead_notification") as mock_task:
        response = client.post(
            "/api/leads/",
            data=payload,
            content_type="application/json",
        )
        assert response.status_code == 201
    lead = Lead.objects.get(pk=response.json()["id"])
    assert lead.assignee_id == lyudmila.pk
    mock_task.delay.assert_called_once_with(lead.pk)


@pytest.mark.django_db
def test_manager_rotation_queryset_requires_group_and_email() -> None:
    """Pool is staff + Менеджер + non-empty email only."""
    ensure_staff_groups()
    ok = _make_manager(username="rr-ok", email="ok@hoocon.ru")
    no_email = User.objects.create_user(
        username="rr-blank",
        email="",
        password="password12",
        is_staff=True,
    )
    no_email.groups.add(Group.objects.get(name=GROUP_MANAGER))
    outsider = User.objects.create_user(
        username="rr-out",
        email="out@hoocon.ru",
        password="password12",
        is_staff=True,
    )
    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert ok.pk in pks
    assert no_email.pk not in pks
    assert outsider.pk not in pks


@pytest.mark.django_db
def test_inactive_manager_excluded_from_rotation_and_notify() -> None:
    """is_active=False: not in RR pool; assign_manager notify falls back to sales@."""
    ensure_staff_groups()
    active = _make_manager(username="rr-active", email="active-mgr@hoocon.ru")
    inactive = User.objects.create_user(
        username="rr-inactive",
        email="inactive-mgr@hoocon.ru",
        password="password12",
        is_staff=True,
        is_active=False,
    )
    inactive.groups.add(Group.objects.get(name=GROUP_MANAGER))

    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert active.pk in pks
    assert inactive.pk not in pks

    site = _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    site.lead_rr_last_user = inactive
    site.save(update_fields=["lead_rr_last_user", "updated_at"])

    lead = Lead.objects.create(
        name="Skip inactive",
        email="skip-inactive@example.com",
        message="x" * 20,
    )
    picked = assign_lead_round_robin(lead)
    assert picked is not None
    assert picked.pk == active.pk
    lead.refresh_from_db()
    assert lead.assignee_id == active.pk

    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_MANAGER)
    orphan = Lead.objects.create(
        name="Inactive assignee",
        email="orphan-inactive@example.com",
        message="x" * 20,
        assignee=inactive,
    )
    with override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru"):
        assert resolve_lead_notify_recipients(orphan) == ["sales@hoocon.ru"]


@pytest.mark.django_db
def test_assign_off_mode_leaves_assignee_empty() -> None:
    """Mode off: assign_lead_round_robin is a no-op."""
    _make_manager(username="rr-off-mgr", email="off-mgr@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.OFF)
    lead = Lead.objects.create(
        name="Off",
        email="off-client@example.com",
        message="x" * 20,
    )
    assert assign_lead_round_robin(lead) is None
    lead.refresh_from_db()
    assert lead.assignee_id is None


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_assign_sales_sets_assignee_and_client() -> None:
    """assign_sales: RR assignee + Client.assignee when empty; notify stays sales@."""
    mgr = _make_manager(username="rr-sales-mgr", email="sales-mgr@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    lead = Lead.objects.create(
        name="Sales mode",
        email="sales-mode@example.com",
        message="x" * 20,
    )
    lead.refresh_from_db()
    assert lead.client_id is not None

    picked = assign_lead_round_robin(lead)
    assert picked is not None
    assert picked.pk == mgr.pk
    lead.refresh_from_db()
    assert lead.assignee_id == mgr.pk
    assert lead.client is not None
    assert lead.client.assignee_id == mgr.pk
    assert resolve_lead_notify_recipients(lead) == ["sales@hoocon.ru"]


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_resolve_recipients_assign_sales_uses_env() -> None:
    """assign_sales notifies LEAD_NOTIFY_EMAIL even when assignee is set."""
    mgr = _make_manager(username="rr-sales-env", email="mgr-env@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    lead = Lead.objects.create(
        name="Env",
        email="env@example.com",
        message="x" * 20,
        assignee=mgr,
    )
    assert resolve_lead_notify_recipients(lead) == ["sales@hoocon.ru"]


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_resolve_recipients_assign_manager_uses_user_email() -> None:
    """assign_manager notifies User.email of assignee."""
    mgr = _make_manager(username="rr-mgr-mail", email="ivan@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_MANAGER)
    lead = Lead.objects.create(
        name="Mgr mail",
        email="client-mgr@example.com",
        message="x" * 20,
        assignee=mgr,
    )
    assert resolve_lead_notify_recipients(lead) == ["ivan@hoocon.ru"]


@pytest.mark.django_db
@override_settings(
    LEAD_NOTIFY_EMAIL="sales@hoocon.ru",
    DEFAULT_FROM_EMAIL="noreply@hoocon.ru",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_send_notification_to_manager_email() -> None:
    """Celery task To: matches assignee login email in assign_manager mode."""
    mgr = _make_manager(username="rr-task-mgr", email="task-mgr@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_MANAGER)
    lead = Lead.objects.create(
        name="Task",
        email="task@example.com",
        message="Проверка письма менеджеру.",
        assignee=mgr,
    )
    send_lead_notification(lead.pk)
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["task-mgr@hoocon.ru"]


@pytest.mark.django_db
def test_round_robin_alternates_two_managers() -> None:
    """Two managers receive leads in alternating order."""
    a = _make_manager(username="rr-a", email="a@hoocon.ru")
    b = _make_manager(username="rr-b", email="b@hoocon.ru")
    # Stable order by pk.
    first, second = (a, b) if a.pk < b.pk else (b, a)
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    lead1 = Lead.objects.create(name="L1", email="l1@example.com", message="x" * 20)
    lead2 = Lead.objects.create(name="L2", email="l2@example.com", message="x" * 20)
    lead3 = Lead.objects.create(name="L3", email="l3@example.com", message="x" * 20)

    assert assign_lead_round_robin(lead1).pk == first.pk
    assert assign_lead_round_robin(lead2).pk == second.pk
    assert assign_lead_round_robin(lead3).pk == first.pk


@pytest.mark.django_db
def test_assign_empty_pool_is_noop() -> None:
    """No managers in pool → no assignee even in assign mode."""
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_MANAGER)
    lead = Lead.objects.create(
        name="Empty pool",
        email="empty-pool@example.com",
        message="x" * 20,
    )
    assert assign_lead_round_robin(lead) is None
    lead.refresh_from_db()
    assert lead.assignee_id is None


@pytest.mark.django_db
def test_scope_hides_assigned_new_from_other_managers() -> None:
    """NEW with assignee is not in the shared pool for other managers."""
    mine = _make_manager(username="scope-rr-mine", email="mine-rr@hoocon.ru")
    other = _make_manager(username="scope-rr-other", email="other-rr@hoocon.ru")
    free = Lead.objects.create(
        name="Free NEW",
        email="free-rr@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
    )
    assigned_new = Lead.objects.create(
        name="Assigned NEW",
        email="assigned-rr@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.NEW,
        assignee=other,
    )
    visible = set(
        scope_leads_for_manager(Lead.objects.all(), mine).values_list("pk", flat=True),
    )
    assert free.pk in visible
    assert assigned_new.pk not in visible

    other_visible = set(
        scope_leads_for_manager(Lead.objects.all(), other).values_list("pk", flat=True),
    )
    assert assigned_new.pk in other_visible


@pytest.mark.django_db(transaction=True)
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_api_assign_sales_sets_assignee(client) -> None:
    """POST /api/leads/ in assign_sales mode sets Lead.assignee."""
    from unittest.mock import patch

    mgr = _make_manager(username="api-rr", email="api-rr@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    payload = {
        "name": "API RR",
        "email": "api-rr-client@example.com",
        "company": "ООО RoundRobin",
        "message": "Заявка через API с автоназначением.",
    }
    with patch("leads.views.send_lead_notification") as mock_task:
        response = client.post(
            "/api/leads/",
            data=payload,
            content_type="application/json",
        )
        assert response.status_code == 201
    lead = Lead.objects.get(pk=response.json()["id"])
    assert lead.assignee_id == mgr.pk
    mock_task.delay.assert_called_once_with(lead.pk)
