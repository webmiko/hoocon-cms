"""Grouped work label checkboxes on Company and Lead change forms."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from crm.models import Company, WorkLabel
from crm.work_label_widget import WorkLabelGroupedWidget, assignable_work_label_queryset, build_work_label_groups
from tests.test_admin_scope_hardening import _admin_change_post

User = get_user_model()


def _work_label_picker_widget(field: object) -> WorkLabelGroupedWidget:
    widget = getattr(field, "widget", field)
    if hasattr(widget, "widget"):
        widget = widget.widget
    assert isinstance(widget, WorkLabelGroupedWidget)
    return widget


def test_build_work_label_groups_orders_by_kind() -> None:
    class _Label:
        def __init__(self, pk: int, name: str, code: str, kind: str) -> None:
            self.pk = pk
            self.name = name
            self.code = code
            self.kind = kind
            self.is_active = True

    groups = build_work_label_groups(
        [
            _Label(1, "Не звонить", "do_not_call", "flag"),
            _Label(2, "Новый лид", "new_lead", "queue"),
        ],
    )
    assert [group.slug for group in groups] == ["queue", "flag"]
    assert groups[0].labels[0].code == "new_lead"


def test_work_label_widget_template_loads_via_form_renderer() -> None:
    from django.forms.renderers import DjangoTemplates

    template = DjangoTemplates().get_template("admin/crm/widgets/grouped_work_labels.html")
    assert "hoocon-perm-picker" in template.template.source


@pytest.mark.django_db
def test_company_change_work_labels_use_grouped_picker(client) -> None:
    admin = User.objects.create_superuser(
        username="work-label-co",
        email="work-label-co@example.com",
        password="password12",
    )
    WorkLabel.objects.create(code="test_queue", name="Тест очередь", kind="queue")
    company = Company.objects.create(name="Тестовая фирма")
    client.force_login(admin)
    response = client.get(reverse("admin:crm_company_change", args=[company.pk]))
    assert response.status_code == 200
    _work_label_picker_widget(response.context["adminform"].form.fields["work_labels"])
    html = response.content.decode()
    assert "data-hoocon-perm-picker" in html
    assert 'class="selector"' not in html.split("work_labels", 1)[1][:4000]
    assert "Очередь" in html or "Флаг" in html


@pytest.mark.django_db
def test_lead_change_work_labels_use_grouped_picker(client, django_user_model) -> None:
    from leads.models import Lead

    admin = django_user_model.objects.create_superuser(
        username="work-label-lead",
        email="work-label-lead@example.com",
        password="password12",
    )
    WorkLabel.objects.create(code="test_flag", name="Тест флаг", kind="flag")
    lead = Lead.objects.create(email="lead@example.com", name="Lead")
    client.force_login(admin)
    url = reverse("admin:leads_lead_change", args=[lead.pk]) + "?edit=1"
    response = client.get(url)
    assert response.status_code == 200
    _work_label_picker_widget(response.context["adminform"].form.fields["work_labels"])
    html = response.content.decode()
    assert "data-hoocon-perm-picker" in html
    assert 'class="selector"' not in html.split("work_labels", 1)[1][:4000]


@pytest.mark.django_db
def test_assignable_work_label_queryset_is_active_only() -> None:
    active = WorkLabel.objects.create(code="active_l", name="Активная", kind="queue", is_active=True)
    inactive = WorkLabel.objects.create(code="inactive_l", name="Выключена", kind="flag", is_active=False)
    qs = assignable_work_label_queryset()
    pks = set(qs.values_list("pk", flat=True))
    assert active.pk in pks
    assert inactive.pk not in pks
    assert not qs.filter(is_active=False).exists()


@pytest.mark.django_db
def test_company_change_work_labels_field_excludes_inactive(client) -> None:
    admin = User.objects.create_superuser(
        username="work-label-qs",
        email="work-label-qs@example.com",
        password="password12",
    )
    active = WorkLabel.objects.create(code="co_active", name="Активная", kind="queue", is_active=True)
    inactive = WorkLabel.objects.create(code="co_inactive", name="Скрытая", kind="flag", is_active=False)
    company = Company.objects.create(name="Фирма метки")
    client.force_login(admin)
    response = client.get(reverse("admin:crm_company_change", args=[company.pk]))
    assert response.status_code == 200
    field = response.context["adminform"].form.fields["work_labels"]
    choice_pks = set(field.queryset.values_list("pk", flat=True))
    assert active.pk in choice_pks
    assert inactive.pk not in choice_pks


@pytest.mark.django_db
def test_company_post_rejects_inactive_work_label(client) -> None:
    admin = User.objects.create_superuser(
        username="work-label-post",
        email="work-label-post@example.com",
        password="password12",
    )
    WorkLabel.objects.create(code="post_active", name="Можно", kind="queue", is_active=True)
    inactive = WorkLabel.objects.create(code="post_inactive", name="Нельзя", kind="flag", is_active=False)
    company = Company.objects.create(name="POST метки")
    client.force_login(admin)
    url = reverse("admin:crm_company_change", args=[company.pk])
    posted = _admin_change_post(client, url)
    posted["work_labels"] = [str(inactive.pk)]
    response = client.post(url, posted)
    assert response.status_code == 200
    assert inactive not in company.work_labels.all()


@pytest.mark.django_db
def test_company_keeps_legacy_inactive_work_label_on_save(client) -> None:
    admin = User.objects.create_superuser(
        username="work-label-legacy",
        email="work-label-legacy@example.com",
        password="password12",
    )
    inactive = WorkLabel.objects.create(code="legacy_in", name="Старая", kind="flag", is_active=False)
    company = Company.objects.create(name="С legacy меткой")
    company.work_labels.add(inactive)
    client.force_login(admin)
    url = reverse("admin:crm_company_change", args=[company.pk])
    posted = _admin_change_post(client, url)
    posted["work_labels"] = [str(inactive.pk)]
    response = client.post(url, posted)
    assert response.status_code == 302, response.status_code
    assert list(company.work_labels.values_list("pk", flat=True)) == [inactive.pk]


@pytest.mark.django_db
def test_lead_post_rejects_inactive_work_label(client) -> None:
    """Lead card uses the same assignable queryset as company (security review M1)."""
    from leads.models import Lead

    admin = User.objects.create_superuser(
        username="work-label-lead-post",
        email="work-label-lead-post@example.com",
        password="password12",
    )
    WorkLabel.objects.create(code="lead_post_active", name="Можно", kind="queue", is_active=True)
    inactive = WorkLabel.objects.create(code="lead_post_inactive", name="Нельзя", kind="flag", is_active=False)
    lead = Lead.objects.create(email="lead-post@example.com", name="Lead POST")
    client.force_login(admin)
    url = reverse("admin:leads_lead_change", args=[lead.pk]) + "?edit=1"
    posted = _admin_change_post(client, url)
    posted["work_labels"] = [str(inactive.pk)]
    response = client.post(url, posted)
    assert response.status_code == 200
    assert inactive not in lead.work_labels.all()


@pytest.mark.django_db
def test_company_post_rejects_foreign_inactive_not_on_card(client) -> None:
    """Legacy inactive A on card must not allow attaching a different inactive B (M2)."""
    admin = User.objects.create_superuser(
        username="work-label-foreign-in",
        email="work-label-foreign-in@example.com",
        password="password12",
    )
    legacy = WorkLabel.objects.create(code="legacy_on_card", name="Старая на карточке", kind="flag", is_active=False)
    foreign = WorkLabel.objects.create(code="foreign_inactive", name="Чужая выключена", kind="queue", is_active=False)
    company = Company.objects.create(name="Две inactive")
    company.work_labels.add(legacy)
    client.force_login(admin)
    url = reverse("admin:crm_company_change", args=[company.pk])
    posted = _admin_change_post(client, url)
    posted["work_labels"] = [str(foreign.pk)]
    response = client.post(url, posted)
    assert response.status_code == 200
    assert foreign not in company.work_labels.all()
    assert list(company.work_labels.values_list("pk", flat=True)) == [legacy.pk]
