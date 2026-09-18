"""Tests for pinned company → manager rules (CompanyManagerRule).

Регресс для правила «assistant@hoocon.ru не участвует в автоматической
постановке и работает только с ООО Атерна»: её исключение из очереди
залочено в коде, а список закреплённых компаний редактируется в Admin.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import override_settings

from accounts.roles import GROUP_MANAGER
from accounts.services import ensure_staff_groups
from crm.models import Client as CrmClient
from leads.models import CompanyManagerRule, Lead
from leads.services import (
    assign_lead_on_create,
    assign_lead_round_robin,
    manager_rotation_queryset,
    resolve_lead_notify_recipients,
)
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


def _make_lead(**overrides: object) -> Lead:
    """Minimal valid lead."""
    defaults = {
        "name": "Клиент",
        "email": "client@example.com",
        "company": "ООО Ромашка",
        "message": "x" * 20,
    }
    defaults.update(overrides)
    return Lead.objects.create(**defaults)


@pytest.mark.django_db
def test_aterna_assignee_excluded_from_rotation_pool() -> None:
    """assistant@hoocon.ru works only with Атерна — never in RR pool.

    Симптом: менеджер в группе «Менеджер» с валидным email попадал в
    общую ротацию. Корень: пул не исключал закреплённого за Атерной
    менеджера — тест лочит инвариант «assistant только Атерна».
    """
    a = _make_manager(username="pool-a", email="pool-a@hoocon.ru")
    assistant = _make_manager(username="assistant", email="assistant@hoocon.ru")

    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert a.pk in pks
    assert assistant.pk not in pks


@pytest.mark.django_db
def test_aterna_assignee_never_picked_by_round_robin() -> None:
    """RR alternates only between ordinary managers, skipping assistant."""
    a = _make_manager(username="rr-skip-a", email="rr-skip-a@hoocon.ru")
    b = _make_manager(username="rr-skip-b", email="rr-skip-b@hoocon.ru")
    _make_manager(username="rr-skip-assistant", email="assistant@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    picks = [assign_lead_round_robin(_make_lead(company=f"ООО Клиент {i}")).pk for i in range(4)]
    assert picks == [a.pk, b.pk, a.pk, b.pk]


@pytest.mark.django_db
def test_pinned_rule_assigns_manager_bypassing_rotation() -> None:
    """Pinned company goes to its manager; RR cursor does not move."""
    a = _make_manager(username="pin-a", email="pin-a@hoocon.ru")
    pinned = _make_manager(username="pin-b", email="pin-b@hoocon.ru")
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=pinned)
    site = _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    site.lead_rr_last_user = a
    site.save(update_fields=["lead_rr_last_user", "updated_at"])

    lead = _make_lead(company="  ооо   «Ромашка»  ")
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == pinned.pk
    lead.refresh_from_db()
    assert lead.assignee_id == pinned.pk
    site.refresh_from_db()
    assert site.lead_rr_last_user_id == a.pk


@pytest.mark.django_db
def test_pinned_rule_normalizes_spelling_variants() -> None:
    """company_key collapses case/quotes/spaces — one rule per company."""
    pinned = _make_manager(username="pin-norm", email="pin-norm@hoocon.ru")
    rule = CompanyManagerRule.objects.create(
        company_label='  ООО  "Ромашка" ',
        assignee=pinned,
    )
    assert rule.company_key == "ооо ромашка"


@pytest.mark.django_db
def test_pinned_rule_ignores_routing_off_mode() -> None:
    """Pinned company assigns its manager even when RR mode is off."""
    pinned = _make_manager(username="pin-off", email="pin-off@hoocon.ru")
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=pinned)
    _set_mode(SiteSettings.LeadRoutingMode.OFF)

    lead = _make_lead(company="ООО Ромашка")
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == pinned.pk


@pytest.mark.django_db
def test_inactive_rule_falls_back_to_rotation() -> None:
    """is_active=False rule is ignored — lead goes to round-robin."""
    a = _make_manager(username="pin-inact-a", email="pin-inact-a@hoocon.ru")
    pinned = _make_manager(username="pin-inact-b", email="pin-inact-b@hoocon.ru")
    CompanyManagerRule.objects.create(
        company_label="ООО Ромашка",
        assignee=pinned,
        is_active=False,
    )
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    lead = _make_lead(company="ООО Ромашка")
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == a.pk


@pytest.mark.django_db
def test_rule_with_inactive_assignee_falls_back_to_rotation() -> None:
    """Pinned rule whose manager was deactivated does not strand the lead."""
    a = _make_manager(username="pin-dead-a", email="pin-dead-a@hoocon.ru")
    pinned = _make_manager(username="pin-dead-b", email="pin-dead-b@hoocon.ru")
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=pinned)
    pinned.is_active = False
    pinned.save(update_fields=["is_active"])
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    lead = _make_lead(company="ООО Ромашка")
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == a.pk


@pytest.mark.django_db
def test_exclusive_rule_removes_manager_from_pool() -> None:
    """exclusive=True: manager gets only pinned companies, not rotation."""
    a = _make_manager(username="excl-a", email="excl-a@hoocon.ru")
    exclusive_mgr = _make_manager(username="excl-b", email="excl-b@hoocon.ru")
    shared = _make_manager(username="excl-c", email="excl-c@hoocon.ru")
    CompanyManagerRule.objects.create(
        company_label="ООО Ромашка",
        assignee=exclusive_mgr,
        exclusive=True,
    )
    CompanyManagerRule.objects.create(
        company_label="ООО Василёк",
        assignee=shared,
        exclusive=False,
    )

    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert a.pk in pks
    assert shared.pk in pks
    assert exclusive_mgr.pk not in pks


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_pinned_rule_notify_goes_to_manager_email() -> None:
    """Pinned company notifies its manager even in assign_sales mode."""
    _make_manager(username="pin-ntf-a", email="pin-ntf-a@hoocon.ru")
    pinned = _make_manager(username="pin-ntf-b", email="pin-ntf-b@hoocon.ru")
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=pinned)
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    lead = _make_lead(company="ООО Ромашка")
    assign_lead_on_create(lead)
    lead.refresh_from_db()
    assert resolve_lead_notify_recipients(lead) == ["pin-ntf-b@hoocon.ru"]


@pytest.mark.django_db
def test_company_owner_keeps_repeat_lead_same_contact() -> None:
    """Repeat lead from an owned contact goes to its manager, not rotation.

    Фича: новый контакт закреплён за менеджером → следующие заявки
    этой компании идут ему же (sticky ownership через Client.assignee).
    """
    a = _make_manager(username="own-a", email="own-a@hoocon.ru")
    _make_manager(username="own-b", email="own-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    first = _make_lead(company="ООО Ромашка", email="ivan@romashka.ru")
    owner = assign_lead_on_create(first)
    assert owner is not None
    assert owner.pk == a.pk

    second = _make_lead(company="ООО «Ромашка»", email="ivan@romashka.ru")
    assert assign_lead_on_create(second).pk == a.pk


@pytest.mark.django_db
def test_company_owner_keeps_lead_from_new_contact() -> None:
    """New email but same company → lead goes to the existing owner."""
    a = _make_manager(username="own2-a", email="own2-a@hoocon.ru")
    _make_manager(username="own2-b", email="own2-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    first = _make_lead(company="ООО Ромашка", email="ivan@romashka.ru")
    owner = assign_lead_on_create(first)
    assert owner is not None
    assert owner.pk == a.pk

    second = _make_lead(company="ооо ромашка", email="olga@romashka.ru")
    picked = assign_lead_on_create(second)
    assert picked is not None
    assert picked.pk == a.pk
    second.refresh_from_db()
    assert second.client is not None
    assert second.client.assignee_id == a.pk


@pytest.mark.django_db
def test_manual_client_assignee_pins_company() -> None:
    """Client.assignee set manually in Admin → company leads route there."""
    mgr = _make_manager(username="own3-mgr", email="own3-mgr@hoocon.ru")
    _make_manager(username="own3-other", email="own3-other@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    CrmClient.objects.create(
        name="Иван",
        email="ivan@romashka.ru",
        company="ООО Ромашка",
        assignee=mgr,
    )

    lead = _make_lead(company="ооо «ромашка»", email="new@romashka.ru")
    picked = assign_lead_on_create(lead)
    assert picked is not None
    assert picked.pk == mgr.pk


@pytest.mark.django_db
def test_pinned_rule_beats_company_owner() -> None:
    """Admin CompanyManagerRule wins over the inherited CRM owner."""
    owner = _make_manager(username="own4-a", email="own4-a@hoocon.ru")
    pinned = _make_manager(username="own4-b", email="own4-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    first = _make_lead(company="ООО Ромашка", email="ivan@romashka.ru")
    assert assign_lead_on_create(first).pk == owner.pk

    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=pinned)
    second = _make_lead(company="ООО Ромашка", email="petr@romashka.ru")
    picked = assign_lead_on_create(second)
    assert picked is not None
    assert picked.pk == pinned.pk


@pytest.mark.django_db
def test_inactive_company_owner_falls_back_to_rotation() -> None:
    """Deactivated owner → next company lead rotates to another manager."""
    a = _make_manager(username="own5-a", email="own5-a@hoocon.ru")
    b = _make_manager(username="own5-b", email="own5-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    first = _make_lead(company="ООО Ромашка", email="ivan@romashka.ru")
    assert assign_lead_on_create(first).pk == a.pk

    a.is_active = False
    a.save(update_fields=["is_active"])
    second = _make_lead(company="ООО Ромашка", email="olga@romashka.ru")
    picked = assign_lead_on_create(second)
    assert picked is not None
    assert picked.pk == b.pk


@pytest.mark.django_db
@override_settings(LEAD_NOTIFY_EMAIL="sales@hoocon.ru")
def test_company_owner_notify_goes_to_manager_email() -> None:
    """Owned company lead notifies the owner even in assign_sales mode."""
    _make_manager(username="own6-a", email="own6-a@hoocon.ru")
    _make_manager(username="own6-b", email="own6-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)

    first = _make_lead(company="ООО Ромашка", email="ivan@romashka.ru")
    assign_lead_on_create(first)

    second = _make_lead(company="ООО Ромашка", email="olga@romashka.ru")
    assign_lead_on_create(second)
    second.refresh_from_db()
    assert resolve_lead_notify_recipients(second) == ["own6-a@hoocon.ru"]
