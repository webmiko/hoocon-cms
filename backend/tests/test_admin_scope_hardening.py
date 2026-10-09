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


@pytest.mark.django_db
def test_analyst_sees_all_leads_and_foreign_clients() -> None:
    """Аналитик is unscoped: foreign in-progress leads and clients are visible."""
    from django.contrib.auth.models import Group

    from accounts.roles import GROUP_ANALYST
    from accounts.services import ensure_staff_groups
    from crm.services import scope_clients_for_manager
    from leads.services import scope_leads_for_manager

    ensure_staff_groups()
    analyst = User.objects.create_user(
        username="analyst-scope",
        email="analyst-scope@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    analyst.groups.add(Group.objects.get(name=GROUP_ANALYST))
    other = User.objects.create_user(
        username="analyst-other-mgr",
        email="analyst-other-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    foreign = CrmClient.objects.create(
        name="Other Buyer",
        email="analyst-foreign@example.com",
        assignee=other,
    )
    foreign_lead = Lead.objects.create(
        name="Other Lead",
        email="analyst-foreign@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
        client=foreign,
    )
    visible_leads = set(
        scope_leads_for_manager(Lead.objects.all(), analyst).values_list("pk", flat=True),
    )
    assert foreign_lead.pk in visible_leads
    visible_clients = set(
        scope_clients_for_manager(CrmClient.objects.all(), analyst).values_list(
            "pk",
            flat=True,
        ),
    )
    assert foreign.pk in visible_clients


@pytest.mark.django_db
def test_analyst_stats_page_includes_other_managers_leads() -> None:
    """Stats for Аналитик are not limited to own assignee scope."""
    from django.contrib.auth.models import Group

    from accounts.roles import GROUP_ANALYST
    from accounts.services import ensure_staff_groups
    from leads.services import build_lead_processing_stats, scope_leads_for_manager

    ensure_staff_groups()
    analyst = User.objects.create_user(
        username="analyst-stats",
        email="analyst-stats@example.com",
        password="password12",
        is_staff=True,
        is_superuser=False,
    )
    analyst.groups.add(Group.objects.get(name=GROUP_ANALYST))
    other = User.objects.create_user(
        username="stats-other-mgr",
        email="stats-other-mgr@example.com",
        password="password12",
        is_staff=True,
    )
    Lead.objects.create(
        name="Theirs IP",
        email="stats-theirs@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
    )
    scoped = scope_leads_for_manager(Lead.objects.all(), analyst)
    stats = build_lead_processing_stats(queryset=scoped)
    assert stats["totals"]["in_progress"] == 1

    client = Client()
    client.force_login(analyst)
    response = client.get(reverse("admin:leads_lead_stats"))
    assert response.status_code == 200


def _foreign_client_pair() -> tuple[User, User, CrmClient, CrmClient]:
    """Manager A, manager B, and a CRM card owned by each."""
    mgr = _staff_with_perms(
        username="scope-row-mgr",
        codenames=(
            "view_client",
            "view_quote",
            "view_order",
            "view_call",
            "view_speclist",
        ),
    )
    other = User.objects.create_user(
        username="scope-row-other",
        email="scope-row-other@example.com",
        password="password12",
        is_staff=True,
    )
    mine = CrmClient.objects.create(
        name="Mine Co",
        email="scope-mine@example.com",
        assignee=mgr,
    )
    foreign = CrmClient.objects.create(
        name="Foreign Co",
        email="scope-foreign@example.com",
        assignee=other,
    )
    Lead.objects.create(
        name="Theirs",
        email="scope-foreign@example.com",
        message="x" * 20,
        status=Lead.LeadStatus.IN_PROGRESS,
        assignee=other,
        client=foreign,
    )
    return mgr, other, mine, foreign


@pytest.mark.django_db
def test_manager_cannot_open_foreign_quote() -> None:
    """Quote changelist/change are scoped — foreign КП are hidden."""
    from crm.models import Quote

    mgr, _other, _mine, foreign = _foreign_client_pair()
    quote = Quote.objects.create(client=foreign)
    page = Client()
    page.force_login(mgr)
    response = page.get(reverse("admin:crm_quote_change", args=[quote.pk]))
    assert response.status_code in (302, 403, 404)
    list_html = page.get(reverse("admin:crm_quote_changelist")).content.decode()
    assert quote.number not in list_html
    assert "scope-foreign@example.com" not in list_html


@pytest.mark.django_db
def test_manager_cannot_open_foreign_order() -> None:
    """Order changelist/change are scoped — foreign заказы are hidden."""
    from cabinet.models import Order

    mgr, _other, _mine, foreign = _foreign_client_pair()
    order = Order.objects.create(client=foreign, number="ORD-FOREIGN-1")
    page = Client()
    page.force_login(mgr)
    response = page.get(reverse("admin:cabinet_order_change", args=[order.pk]))
    assert response.status_code in (302, 403, 404)
    list_html = page.get(reverse("admin:cabinet_order_changelist")).content.decode()
    assert "ORD-FOREIGN-1" not in list_html


@pytest.mark.django_db
def test_manager_cannot_see_foreign_linked_call() -> None:
    """Call journal hides other managers' client-linked rows (PII)."""
    from crm.models import Call, CallDirection

    mgr, _other, _mine, foreign = _foreign_client_pair()
    Call.objects.create(
        entry_id="scope-call-foreign",
        direction=CallDirection.INBOUND,
        from_number="79151110000",
        client=foreign,
    )
    Call.objects.create(
        entry_id="scope-call-orphan",
        direction=CallDirection.INBOUND,
        from_number="79152220000",
    )
    page = Client()
    page.force_login(mgr)
    list_html = page.get(reverse("admin:crm_call_changelist")).content.decode()
    assert "79151110000" not in list_html
    assert "79152220000" in list_html


def test_every_custom_admin_action_declares_permissions() -> None:
    """Actions без allowed_permissions были доступны роли «только просмотр» (Аналитик)."""
    import inspect
    from pathlib import Path

    from django.conf import settings
    from django.contrib.admin.sites import site

    root = Path(settings.BASE_DIR).resolve()

    def ours(model_admin) -> bool:
        path = Path(inspect.getfile(type(model_admin))).resolve()
        return path.is_relative_to(root) and ".venv" not in path.parts

    project_admins = [ma for ma in site._registry.values() if ours(ma)]  # noqa: SLF001
    assert len(project_admins) > 10
    missing = [
        f"{type(model_admin).__name__}.{name}"
        for model_admin in project_admins
        for func, name, _desc in model_admin._get_base_actions()  # noqa: SLF001
        if name != "delete_selected" and not getattr(func, "allowed_permissions", None)
    ]
    assert missing == []


@pytest.mark.django_db
def test_view_only_staff_gets_no_mutating_lead_or_client_actions() -> None:
    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    from crm.admin import ClientAdmin, CompanyAdmin
    from crm.models import Company
    from leads.admin import LeadAdmin

    viewer = _staff_with_perms(
        username="view-only-actions",
        codenames=("view_lead", "view_client", "view_company", "change_company"),
    )
    request = RequestFactory().get("/admin/")
    request.user = viewer
    assert LeadAdmin(Lead, site).get_actions(request) == {}
    assert ClientAdmin(CrmClient, site).get_actions(request) == {}
    assert "merge_companies_action" not in CompanyAdmin(Company, site).get_actions(request)


def _fk_field(admin_cls, model, field: str, user, object_id: int | None = None):
    """Admin form field for ``field`` exactly as the change form builds it."""
    from types import SimpleNamespace

    from django.contrib.admin.sites import site
    from django.test import RequestFactory

    request = RequestFactory().get("/admin/")
    request.user = user
    request.resolver_match = SimpleNamespace(kwargs={"object_id": str(object_id)} if object_id else {})
    return admin_cls(model, site).formfield_for_foreignkey(model._meta.get_field(field), request)


@pytest.mark.django_db
def test_manager_cannot_relink_own_lead_to_foreign_client() -> None:
    """Autocomplete принимал любой pk: менеджер привязывал свой лид к чужому клиенту и видел его письма/КП."""
    from django.core.exceptions import ValidationError

    from crm.services import scope_clients_for_manager
    from leads.admin import LeadAdmin

    mgr, _other, mine, foreign = _foreign_client_pair()
    own_lead = Lead.objects.create(
        name="Mine", email="mine-lead@example.com", message="x" * 20, assignee=mgr, client=mine
    )
    field = _fk_field(LeadAdmin, Lead, "client", mgr, own_lead.pk)
    assert field.clean(mine.pk) == mine
    with pytest.raises(ValidationError):
        field.clean(foreign.pk)
    assert foreign.pk not in set(scope_clients_for_manager(CrmClient.objects.all(), mgr).values_list("pk", flat=True))


@pytest.mark.django_db
def test_scoped_fk_keeps_value_linked_by_automation() -> None:
    """Лид, привязанный по email к чужой карточке, всё ещё сохраняется своим менеджером."""
    from leads.admin import LeadAdmin

    mgr, _other, _mine, foreign = _foreign_client_pair()
    auto_linked = Lead.objects.create(name="Auto", email=foreign.email, message="x" * 20, assignee=mgr, client=foreign)
    field = _fk_field(LeadAdmin, Lead, "client", mgr, auto_linked.pk)
    assert field.clean(foreign.pk) == foreign


@pytest.mark.django_db
def test_crm_admins_scope_client_lead_quote_order_pickers() -> None:
    """Quote/Call/ClientDocument/Activity/Email принимали чужие client/lead/quote/order."""
    from django.core.exceptions import ValidationError

    from cabinet.models import Order
    from crm.admin import ActivityAdmin, CallAdmin, ClientDocumentAdmin, EmailMessageAdmin, QuoteAdmin
    from crm.models import Call, ClientDocument, EmailMessage, Quote

    mgr, _other, mine, foreign = _foreign_client_pair()
    foreign_lead = Lead.objects.get(client=foreign)
    foreign_quote = Quote.objects.create(client=foreign)
    foreign_order = Order.objects.create(client=foreign, number="ORD-SCOPE-FK")
    for admin_cls, model in (
        (QuoteAdmin, Quote),
        (CallAdmin, Call),
        (ActivityAdmin, Activity),
        (EmailMessageAdmin, EmailMessage),
        (ClientDocumentAdmin, ClientDocument),
    ):
        client_field = _fk_field(admin_cls, model, "client", mgr)
        assert client_field.clean(mine.pk) == mine
        with pytest.raises(ValidationError):
            client_field.clean(foreign.pk)
        if admin_cls is not ClientDocumentAdmin:
            with pytest.raises(ValidationError):
                _fk_field(admin_cls, model, "lead", mgr).clean(foreign_lead.pk)
    with pytest.raises(ValidationError):
        _fk_field(ClientDocumentAdmin, ClientDocument, "quote", mgr).clean(foreign_quote.pk)
    with pytest.raises(ValidationError):
        _fk_field(ClientDocumentAdmin, ClientDocument, "order", mgr).clean(foreign_order.pk)


def test_activity_author_is_read_only_in_admin() -> None:
    """Подделка автора заметки расширяла видимость карточки другому менеджеру."""
    from django.contrib.admin.sites import site

    from crm.admin import ActivityAdmin, ActivityInline
    from crm.models import Client as CrmModel

    assert "author" in ActivityAdmin(Activity, site).readonly_fields
    assert "author" not in ActivityAdmin.autocomplete_fields
    assert "author" in ActivityInline(CrmModel, site).readonly_fields


@pytest.mark.django_db
def test_manager_cannot_open_foreign_spec_list() -> None:
    """Cabinet spec templates follow CRM client visibility."""
    from accounts.models import ClientAccount
    from cabinet.models import SpecList

    mgr, _other, _mine, foreign = _foreign_client_pair()
    account = ClientAccount.objects.create(email=foreign.email, name="Foreign Acc")
    foreign.account = account
    foreign.save(update_fields=["account"])
    spec = SpecList.objects.create(account=account, name="Чужая спецификация")
    page = Client()
    page.force_login(mgr)
    response = page.get(reverse("admin:cabinet_speclist_change", args=[spec.pk]))
    assert response.status_code in (302, 403, 404)
    list_html = page.get(reverse("admin:cabinet_speclist_changelist")).content.decode()
    assert "Чужая спецификация" not in list_html
