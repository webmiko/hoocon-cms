"""Grouped permission checkboxes on auth Group / User change forms."""

from __future__ import annotations

import pytest
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.urls import reverse

from config.admin_permissions import (
    AuthGroupCheckboxWidget,
    GroupedPermissionWidget,
    _app_verbose_name,
    _codename_sort_key,
    _humanize_model_slug,
    _model_label_from_can_permission,
    _resolve_model_label,
    build_permission_groups,
    install_admin_permission_pickers,
    ordered_permission_queryset,
    permission_action_key,
    permission_action_label,
)

User = get_user_model()


@pytest.mark.django_db
def test_group_add_uses_grouped_permission_picker(client) -> None:
    admin = User.objects.create_superuser(
        username="perm-picker-add",
        email="perm-picker-add@example.com",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_group_add"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "data-hoocon-perm-picker" in html
    assert 'class="selector"' not in html


@pytest.mark.django_db
def test_group_change_uses_grouped_permission_picker_not_dual_list(client) -> None:
    admin = User.objects.create_superuser(
        username="perm-picker-admin",
        email="perm-picker-admin@example.com",
        password="password12",
    )
    group = Group.objects.create(name="Менеджер-test")
    client.force_login(admin)
    response = client.get(reverse("admin:auth_group_change", args=[group.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert "data-hoocon-perm-picker" in html
    assert 'class="selector"' not in html
    assert "hoocon-admin-permissions.js" in html


@pytest.mark.django_db
def test_user_change_user_permissions_use_grouped_picker(client) -> None:
    admin = User.objects.create_superuser(
        username="perm-user-admin",
        email="perm-user-admin@example.com",
        password="password12",
    )
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_change", args=[admin.pk]))
    assert response.status_code == 200
    html = response.content.decode()
    assert html.count("data-hoocon-perm-picker") >= 1
    assert "field-user_permissions" in html
    user_perm_block = html.split("field-user_permissions", 1)[1].split("field-", 1)[0]
    assert 'class="selector"' not in user_perm_block


@pytest.mark.django_db
def test_user_change_groups_use_checkbox_picker_not_dual_list(client) -> None:
    admin = User.objects.create_superuser(
        username="perm-groups-admin",
        email="perm-groups-admin@example.com",
        password="password12",
    )
    Group.objects.create(name="Менеджер-test")
    client.force_login(admin)
    response = client.get(reverse("admin:auth_user_change", args=[admin.pk]))
    assert response.status_code == 200
    groups_field = response.context["adminform"].form.fields["groups"]
    widget = groups_field.widget.widget if hasattr(groups_field.widget, "widget") else groups_field.widget
    assert isinstance(widget, AuthGroupCheckboxWidget)
    html = response.content.decode()
    assert "hoocon-auth-groups-picker" in html
    assert 'class="selector"' not in html.split("groups", 1)[1][:4000]


@pytest.mark.django_db
def test_group_permissions_save_via_checkboxes(client) -> None:
    admin = User.objects.create_superuser(
        username="perm-save-admin",
        email="perm-save-admin@example.com",
        password="password12",
    )
    perm = Permission.objects.filter(codename="view_lead").first()
    assert perm is not None
    group = Group.objects.create(name="perm-save-group")
    client.force_login(admin)
    url = reverse("admin:auth_group_change", args=[group.pk])
    post = client.post(
        url,
        {
            "name": group.name,
            "permissions": [str(perm.pk)],
        },
    )
    assert post.status_code == 302
    group.refresh_from_db()
    assert list(group.permissions.values_list("pk", flat=True)) == [perm.pk]


def test_humanize_model_slug_splits_leadelegationstate() -> None:
    assert _humanize_model_slug("leadelegationstate") == "Lead delegation state"


def test_codename_sort_key_puts_custom_permissions_last() -> None:
    assert _codename_sort_key("custom_perm")[0] == 99


def test_app_verbose_name_falls_back_to_label_on_unknown_app() -> None:
    assert _app_verbose_name("definitely_not_an_installed_app_label") == "definitely_not_an_installed_app_label"


def test_model_label_from_can_permission_rejects_non_can_prefix() -> None:
    assert _model_label_from_can_permission("View lead") is None


def test_model_label_from_can_permission_strips_change_verb() -> None:
    assert _model_label_from_can_permission("Can change lead") == "lead"


def test_resolve_model_label_uses_content_type_name_before_humanize(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Meta:
        verbose_name = "lead"

    class _Model:
        _meta = _Meta()

    monkeypatch.setattr("config.admin_permissions.apps.get_model", lambda _a, _m: _Model())
    label = _resolve_model_label(
        "leads",
        "lead",
        "Клиентский лид",
        ["Can view lead"],
    )
    assert label == "Клиентский лид"


def test_grouped_permission_widget_context_marks_selected_ids() -> None:
    widget = GroupedPermissionWidget(queryset=Permission.objects.none())
    context = widget.get_context("permissions", ["7", 8], {})
    assert context["selected_ids"] == {"7", "8"}
    assert context["standard_bulk_actions"]


def test_grouped_permission_widget_value_from_datadict_handles_all_shapes() -> None:
    from django.utils.datastructures import MultiValueDict

    widget = GroupedPermissionWidget()
    data = MultiValueDict({"permissions": ["1", "2"]})
    assert widget.value_from_datadict(data, {}, "permissions") == ["1", "2"]
    assert widget.value_from_datadict({"permissions": "3"}, {}, "permissions") == ["3"]
    assert widget.value_from_datadict({"permissions": ["4"]}, {}, "permissions") == ["4"]
    assert widget.value_from_datadict({}, {}, "permissions") == []


def test_auth_group_widget_value_from_datadict_handles_all_shapes() -> None:
    from django.utils.datastructures import MultiValueDict

    widget = AuthGroupCheckboxWidget(queryset=Group.objects.none())
    data = MultiValueDict({"groups": ["1"]})
    assert widget.value_from_datadict(data, {}, "groups") == ["1"]
    assert widget.value_from_datadict({"groups": "2"}, {}, "groups") == ["2"]
    assert widget.value_from_datadict({}, {}, "groups") == []


def test_install_admin_permission_pickers_is_idempotent() -> None:
    install_admin_permission_pickers()


@pytest.mark.django_db
def test_ordered_permission_queryset_is_select_related() -> None:
    perm = ordered_permission_queryset().first()
    assert perm is not None
    assert perm.content_type.app_label


def test_model_label_from_can_permission_strips_view_verb() -> None:
    assert _model_label_from_can_permission("Can view lead delegation state") == "lead delegation state"


def test_resolve_model_label_uses_permission_name_when_meta_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _missing_model(app_label: str, model: str) -> None:
        raise LookupError(app_label, model)

    monkeypatch.setattr("config.admin_permissions.apps.get_model", _missing_model)
    label = _resolve_model_label(
        "crm",
        "leadelegationstate",
        "leadelegationstate",
        ["Can view lead delegation state"],
    )
    assert label == "lead delegation state"


def test_permission_action_key_maps_standard_codenames() -> None:
    assert permission_action_key("view_lead") == "view"
    assert permission_action_key("custom_perm") == "other"


def test_permission_action_label_maps_standard_codenames() -> None:
    assert permission_action_label("view_lead", "Can view lead") == "Просмотр"
    assert permission_action_label("add_client", "Can add client") == "Добавление"
    assert permission_action_label("custom_perm", "Can do magic") == "do magic"


def test_grouped_permission_widget_template_loads_via_form_renderer() -> None:
    """Widget template lives under accounts/templates for DjangoTemplates renderer."""
    from django.forms.renderers import DjangoTemplates

    template = DjangoTemplates().get_template("admin/widgets/grouped_permissions.html")
    source = template.template.source
    assert "hoocon-perm-picker" in source
    assert "hoocon-perm-picker__bulk-toggle" in source
    assert "data-hoocon-perm-bulk-action" in source
    assert "data-hoocon-perm-action" in source


def test_auth_groups_widget_template_loads_via_form_renderer() -> None:
    from django.forms.renderers import DjangoTemplates

    template = DjangoTemplates().get_template("admin/widgets/auth_groups_checkbox.html")
    assert "hoocon-auth-groups-picker" in template.template.source


def test_unfold_scripts_include_permissions_picker_on_group_form() -> None:
    from django.test import RequestFactory

    from config.unfold_callbacks import admin_permissions_picker_js

    request = RequestFactory().get("/admin/auth/group/add/")
    assert "hoocon-admin-permissions.js" in admin_permissions_picker_js(request)
    assert "hoocon-noop.js" in admin_permissions_picker_js(RequestFactory().get("/admin/leads/lead/"))


def test_install_admin_permission_pickers_patches_base_model_admin() -> None:
    from django.contrib.admin.options import BaseModelAdmin

    assert getattr(BaseModelAdmin.formfield_for_manytomany, "_hoocon_permission_pickers", False)


@pytest.mark.django_db
def test_permission_m2m_clean_rejects_pk_outside_queryset() -> None:
    """Grouped picker still relies on ModelMultipleChoiceField validation."""
    perm_in = Permission.objects.filter(codename="view_lead").first()
    perm_out = Permission.objects.exclude(pk=perm_in.pk).first()
    assert perm_in is not None and perm_out is not None
    field = forms.ModelMultipleChoiceField(queryset=Permission.objects.filter(pk=perm_in.pk))
    with pytest.raises(ValidationError):
        field.clean([str(perm_out.pk)])


def test_build_permission_groups_sorts_view_before_delete() -> None:
    class _Ct:
        app_label = "leads"
        model = "lead"
        name = "lead"

    class _Perm:
        def __init__(self, pk: int, codename: str, name: str) -> None:
            self.pk = pk
            self.codename = codename
            self.name = name
            self.content_type = _Ct()

    groups = build_permission_groups(
        [
            _Perm(2, "delete_lead", "Can delete lead"),
            _Perm(1, "view_lead", "Can view lead"),
        ],
    )
    assert len(groups) == 1
    perms = groups[0].models[0].permissions
    assert [p.codename for p in perms] == ["view_lead", "delete_lead"]


def test_grouped_permission_picker_css_in_unfold_extras() -> None:
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css").read_text(
        encoding="utf-8",
    )
    assert ".hoocon-perm-picker" in css
    picker_wrap = css.split(".related-widget-wrapper:has(.hoocon-perm-picker)", 1)[1]
    assert "display: block !important" in picker_wrap.split("}", 1)[0]
    assert "relatedWidgetWrapper" in picker_wrap
    assert "display: none !important" in picker_wrap
    app_gap = css.split(".hoocon-perm-picker > .hoocon-perm-picker__app + .hoocon-perm-picker__app", 1)[1].split(
        "}",
        1,
    )[0]
    assert "margin-top: 1rem !important" in app_gap
    list_rule = css.split(".hoocon-perm-picker__list {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in list_rule
    perm_mobile = css.split(".field-permissions.field-line", 1)[1].split("}", 3)[0]
    assert "flex-direction: column" in perm_mobile
    perm_section = css.split("/* Auth Group / User — permissions", 1)[1]
    mobile_block = perm_section.split("@media (max-width: 767px) {", 1)[1]
    mobile_list = mobile_block.split(".hoocon-perm-picker__list", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr" in mobile_list
    assert ".hoocon-perm-picker__bulk-toggle" in css
