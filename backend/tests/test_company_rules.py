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
    sync_company_pin,
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
def test_pinned_only_is_one_switch_per_manager() -> None:
    """One queue switch removes the manager. A second company does not need its own flag."""
    from leads.models import ManagerQueueMode

    a = _make_manager(username="excl-a", email="excl-a@hoocon.ru")
    exclusive_mgr = _make_manager(username="excl-b", email="excl-b@hoocon.ru")
    shared = _make_manager(username="excl-c", email="excl-c@hoocon.ru")
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=exclusive_mgr)
    CompanyManagerRule.objects.create(company_label="ООО Лютик", assignee=exclusive_mgr)
    CompanyManagerRule.objects.create(company_label="ООО Василёк", assignee=shared)
    ManagerQueueMode.objects.create(assignee=exclusive_mgr, pinned_only=True)

    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert a.pk in pks
    assert shared.pk in pks
    assert exclusive_mgr.pk not in pks
    assert ManagerQueueMode.objects.filter(assignee=exclusive_mgr).count() == 1


@pytest.mark.django_db
def test_last_pin_returns_manager_to_the_shared_queue() -> None:
    """Removing the last company clears the switch. A leftover switch must not swallow leads."""
    from crm.models import Company
    from leads.models import ManagerQueueMode

    waiting = _make_manager(username="last-a", email="last-a@hoocon.ru")
    pinned = _make_manager(username="last-b", email="last-b@hoocon.ru")
    org = Company.objects.create(name="ООО Ромашка", assignee=pinned)
    CompanyManagerRule.objects.create(company_label=org.name, assignee=pinned)
    ManagerQueueMode.objects.create(assignee=pinned, pinned_only=True)

    sync_company_pin(org, pinned=False)

    mode = ManagerQueueMode.objects.get(assignee=pinned)
    assert mode.pinned_only is False
    pks = set(manager_rotation_queryset().values_list("pk", flat=True))
    assert pinned.pk in pks
    assert waiting.pk in pks

    ManagerQueueMode.objects.filter(assignee=pinned).update(pinned_only=True)
    assert pinned.pk in set(manager_rotation_queryset().values_list("pk", flat=True))


@pytest.mark.django_db
def test_lead_follows_the_company_card_when_the_pin_is_stale() -> None:
    """A lead uses the card's manager before anyone opens the pinned list."""
    from crm.models import Company

    former = _make_manager(username="stale-a", email="stale-a@hoocon.ru")
    current = _make_manager(username="stale-b", email="stale-b@hoocon.ru")
    Company.objects.create(name="ООО Ромашка", assignee=current)
    CompanyManagerRule.objects.create(company_label="ООО Ромашка", assignee=former)

    lead = _make_lead(company="ООО Ромашка")
    picked = assign_lead_on_create(lead)

    assert picked is not None
    assert picked.pk == current.pk
    card = Company.objects.get(name="ООО Ромашка")
    assert card.assignee_id == current.pk
    assert CompanyManagerRule.objects.get(company_key=card.company_key).assignee_id == current.pk


@pytest.mark.django_db
def test_assign_to_me_moves_the_pin_with_the_card(client) -> None:
    """«Назначить меня» writes the card past save_model and still moves the pin."""
    from django.urls import reverse

    from crm.models import Company

    former = _make_manager(username="claim-a", email="claim-a@hoocon.ru")
    org = Company.objects.create(name="ООО Свободная")
    CompanyManagerRule.objects.create(company_label=org.name, assignee=former)
    admin = User.objects.create_superuser("claim-admin", "claim-admin@hoocon.ru", "password12")
    client.force_login(admin)

    response = client.post(
        reverse("admin:crm_company_changelist"),
        {"action": "assign_to_me", "_selected_action": [str(org.pk)]},
    )

    assert response.status_code == 302
    org.refresh_from_db()
    assert org.assignee_id == admin.pk
    assert CompanyManagerRule.objects.get(company_key=org.company_key).assignee_id == admin.pk


@pytest.mark.django_db
def test_taking_a_free_call_moves_the_pin_with_the_company(client) -> None:
    """Claiming a call writes the company past the card form and still moves the pin."""
    from django.urls import reverse
    from django.utils import timezone

    from crm.models import Company, PlannedTouch

    former = _make_manager(username="call-a", email="call-a@hoocon.ru")
    org = Company.objects.create(name="ООО Звонок")
    CompanyManagerRule.objects.create(company_label=org.name, assignee=former)
    touch = PlannedTouch.objects.create(company=org, title="Позвонить", starts_at=timezone.now())
    admin = User.objects.create_superuser("call-admin", "call-admin@hoocon.ru", "password12")
    client.force_login(admin)

    response = client.post(reverse("admin:crm_plannedtouch_assign_me", args=[touch.pk]))

    assert response.status_code == 302
    org.refresh_from_db()
    assert org.assignee_id == admin.pk
    assert CompanyManagerRule.objects.get(company_key=org.company_key).assignee_id == admin.pk


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


@pytest.mark.django_db
def test_new_lead_stays_unassigned_even_on_a_pinned_client() -> None:
    """A new lead is not given to the manager who already owns the client card."""
    mgr = _make_manager(username="inh-a", email="inh-a@hoocon.ru")
    _make_manager(username="inh-b", email="inh-b@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.OFF)
    CrmClient.objects.create(
        name="Иван",
        email="ivan@corp-inh.ru",
        company="",
        assignee=mgr,
    )

    lead = _make_lead(company="", email="ivan@corp-inh.ru")

    lead.refresh_from_db()
    assert lead.client is not None
    assert lead.client.assignee_id == mgr.pk
    assert lead.assignee_id is None


@pytest.mark.django_db
def test_inactive_client_owner_not_inherited() -> None:
    """Неактивный владелец карточки → заявка остаётся в общем пуле."""
    mgr = _make_manager(username="inh-c", email="inh-c@hoocon.ru")
    mgr.is_active = False
    mgr.save(update_fields=["is_active"])
    _set_mode(SiteSettings.LeadRoutingMode.OFF)
    CrmClient.objects.create(
        name="Иван",
        email="ivan@corp-inh2.ru",
        company="",
        assignee=mgr,
    )

    lead = _make_lead(company="", email="ivan@corp-inh2.ru")

    lead.refresh_from_db()
    assert lead.assignee_id is None


@pytest.mark.django_db
def test_pipeline_honors_client_owner_without_company() -> None:
    """assign_lead_on_create: владелец карточки идёт до ротации даже при
    пустом lead.company — RR-курсор не тратится на чужого клиента."""
    owner = _make_manager(username="inh-d", email="inh-d@hoocon.ru")
    _make_manager(username="inh-e", email="inh-e@hoocon.ru")
    _set_mode(SiteSettings.LeadRoutingMode.ASSIGN_SALES)
    CrmClient.objects.create(
        name="Иван",
        email="ivan@corp-inh3.ru",
        company="",
        assignee=owner,
    )

    lead = _make_lead(company="", email="ivan@corp-inh3.ru")
    picked = assign_lead_on_create(lead)

    assert picked is not None
    assert picked.pk == owner.pk


@pytest.mark.django_db
def test_pinned_list_groups_companies_and_one_queue_switch(client) -> None:
    """The list gathers companies under a manager and does not repeat the queue switch."""
    from pathlib import Path

    from django.urls import reverse

    from leads.models import ManagerQueueMode

    lyuda = _make_manager(username="grp-l", email="grp-l@hoocon.ru")
    lyuda.first_name = "Людмила"
    lyuda.save(update_fields=["first_name"])
    other = _make_manager(username="grp-v", email="grp-v@hoocon.ru")
    other.first_name = "Валерия"
    other.save(update_fields=["first_name"])
    CompanyManagerRule.objects.create(company_label="Демо Альфа", assignee=lyuda)
    CompanyManagerRule.objects.create(company_label="Демо Бета", assignee=lyuda)
    CompanyManagerRule.objects.create(company_label="Демо Эпсилон", assignee=other)
    admin = User.objects.create_superuser("grp-admin", "grp-admin@hoocon.ru", "password12")
    client.force_login(admin)

    page = client.get(reverse("admin:leads_companymanagerrule_changelist"))
    html = page.content.decode()
    assert page.status_code == 200
    assert 'name="exclusive"' not in html
    assert "hoocon-admin-pinned-companies.js" in html
    assert html.index("Демо Эпсилон") < html.index("Демо Альфа") < html.index("Демо Бета")
    assert html.count(f'data-assignee-id="{lyuda.pk}"') == 3
    assert html.count(f'data-assignee-id="{other.pk}"') == 2
    assert html.count('data-off="В общей очереди"') == 2
    assert html.count('data-on="Только закреплённые"') == 2
    assert html.count("Сохранено") == 2
    assert "hoocon-pinned-assignee" not in html
    # source-lint: the script the changelist loads rolls the switch back and says it saved
    script = (Path(__file__).resolve().parents[1] / "static/admin/js/hoocon-admin-pinned-companies.js").read_text(
        encoding="utf-8"
    )
    assert "hoocon-pinned-manager" in script
    assert "data-assignee-id" in script
    assert ".catch(" in script
    assert "hoocon-pinned-manager__saved" in script
    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8",
    )
    assert css.count(".hoocon-pinned-manager__cards a") == 3
    assert "hoocon-pinned-group" not in css
    card = css.split(".hoocon-pinned-manager {", 1)[1].split("}", 1)[0]
    assert "border-radius: var(--hoocon-radius)" in card
    assert "padding: var(--hoocon-card-pad)" in card
    assert "background: var(--hoocon-surface)" in card
    chip = css.split("body.hoocon-pinned-companies .hoocon-pinned-manager__cards a,", 1)[1].split("}", 1)[0]
    assert "color: var(--hoocon-ink)" in chip
    assert "background: var(--hoocon-surface-muted)" in chip
    assert "padding: var(--hoocon-chip-pad)" in chip
    assert "#" not in chip

    saved = client.post(
        reverse("admin:leads_companymanagerrule_queue_mode"),
        {"assignee": str(lyuda.pk), "pinned_only": "1"},
    )
    assert saved.status_code == 302
    assert ManagerQueueMode.objects.get(assignee=lyuda).pinned_only is True
    assert ManagerQueueMode.objects.filter(assignee=other).count() == 0
    assert lyuda.pk not in set(manager_rotation_queryset().values_list("pk", flat=True))
    assert other.pk in set(manager_rotation_queryset().values_list("pk", flat=True))

    from crm.models import Company
    from tests.admin_form import _admin_change_post  # shared form replay, not another test module

    firm = Company.objects.create(name="ООО «Демо Закрепление»")
    before = Company.objects.count()
    card_url = reverse("admin:crm_company_change", args=[firm.pk])
    card = client.get(card_url)
    assert card.status_code == 200
    assert "В списке закреплённых" in card.content.decode()
    posted = _admin_change_post(client, card_url)
    posted["assignee"] = str(lyuda.pk)
    posted["pin_for_leads"] = "on"
    saved = client.post(card_url, posted)
    assert saved.status_code == 302
    rule = CompanyManagerRule.objects.get(company_key=firm.company_key)
    assert rule.assignee_id == lyuda.pk
    assert Company.objects.count() == before
    opened = client.get(reverse("admin:leads_companymanagerrule_change", args=[rule.pk]))
    assert opened.status_code == 302
    assert opened.url == card_url
    added = client.get(reverse("admin:leads_companymanagerrule_add"))
    assert added.status_code == 403

    cleared = _admin_change_post(client, card_url)
    cleared.pop("pin_for_leads", None)
    cleared["assignee"] = str(lyuda.pk)
    again = client.post(card_url, cleared)
    assert again.status_code == 302
    assert not CompanyManagerRule.objects.filter(company_key=firm.company_key).exists()

    bare = _admin_change_post(client, card_url)
    bare.pop("assignee", None)
    bare["pin_for_leads"] = "on"
    refused = client.post(card_url, bare)
    assert refused.status_code == 200
    assert "ответственного" in refused.content.decode()
    assert not CompanyManagerRule.objects.filter(company_key=firm.company_key).exists()

    stranger = User.objects.create_user("grp-no", password="x", is_staff=True)
    client.force_login(stranger)
    denied = client.post(
        reverse("admin:leads_companymanagerrule_queue_mode"),
        {"assignee": str(other.pk), "pinned_only": "1"},
    )
    assert denied.status_code == 403
    assert not ManagerQueueMode.objects.filter(assignee=other, pinned_only=True).exists()


@pytest.mark.django_db
def test_pinned_list_keeps_each_companys_assignee(client) -> None:
    """A drifted pin follows the company card. The card is not given to one manager."""
    from django.urls import reverse

    from crm.models import Company

    lyuda = _make_manager(username="keep-l", email="keep-l@hoocon.ru")
    lyuda.first_name = "Людмила"
    lyuda.save(update_fields=["first_name"])
    other = _make_manager(username="keep-v", email="keep-v@hoocon.ru")
    other.first_name = "Валерия"
    other.save(update_fields=["first_name"])
    hers = Company.objects.create(name="Карточка Валерии", assignee=other)
    his = Company.objects.create(name="Карточка Людмилы", assignee=lyuda)
    CompanyManagerRule.objects.create(company_label=hers.name, assignee=lyuda)
    CompanyManagerRule.objects.create(company_label=his.name, assignee=lyuda)
    admin = User.objects.create_superuser("keep-admin", "keep-admin@hoocon.ru", "password12")
    client.force_login(admin)

    page = client.get(reverse("admin:leads_companymanagerrule_changelist"))
    html = page.content.decode()
    assert page.status_code == 200
    hers.refresh_from_db()
    his.refresh_from_db()
    assert hers.assignee_id == other.pk
    assert his.assignee_id == lyuda.pk
    assert CompanyManagerRule.objects.get(company_key=hers.company_key).assignee_id == other.pk
    assert CompanyManagerRule.objects.get(company_key=his.company_key).assignee_id == lyuda.pk
    assert html.index("Валерия") < html.index("Карточка Валерии")
    assert html.index("Карточка Валерии") < html.index("Людмила")
    assert html.index("Людмила") < html.index("Карточка Людмилы")


@pytest.mark.django_db
def test_pinned_list_does_not_rewrite_rows_without_permission(client) -> None:
    """A staff user who cannot open the list does not move pins or reach a company card."""
    from django.urls import reverse

    from crm.models import Company

    former = _make_manager(username="deny-a", email="deny-a@hoocon.ru")
    current = _make_manager(username="deny-b", email="deny-b@hoocon.ru")
    org = Company.objects.create(name="ООО Закрыто", assignee=current)
    rule = CompanyManagerRule.objects.create(company_label=org.name, assignee=former)
    stranger = User.objects.create_user("deny-staff", password="x", is_staff=True)
    client.force_login(stranger)

    listing = client.get(reverse("admin:leads_companymanagerrule_changelist"))
    opened = client.get(reverse("admin:leads_companymanagerrule_change", args=[rule.pk]))

    assert listing.status_code == 403
    assert opened.status_code == 403
    rule.refresh_from_db()
    assert rule.assignee_id == former.pk
    org.refresh_from_db()
    assert org.assignee_id == current.pk


@pytest.mark.django_db
def test_queue_switch_skips_staff_outside_the_manager_group(client) -> None:
    """An analyst keeps a pin row, but the queue switch does not create a mode for them."""
    from django.urls import reverse

    from leads.models import ManagerQueueMode

    analyst = User.objects.create_user("pin-analyst", password="x", is_staff=True, is_active=True)
    CompanyManagerRule.objects.create(company_label="ООО Аналитик", assignee=analyst)
    admin = User.objects.create_superuser("pin-queue-admin", "pin-queue-admin@hoocon.ru", "password12")
    client.force_login(admin)

    page = client.get(reverse("admin:leads_companymanagerrule_changelist"))
    html = page.content.decode()
    assert page.status_code == 200
    assert f'data-assignee-id="{analyst.pk}"' in html
    assert 'data-off="В общей очереди"' not in html

    denied = client.post(
        reverse("admin:leads_companymanagerrule_queue_mode"),
        {"assignee": str(analyst.pk), "pinned_only": "1"},
    )
    assert denied.status_code == 403
    assert not ManagerQueueMode.objects.filter(assignee=analyst).exists()
