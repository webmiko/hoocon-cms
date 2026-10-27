"""Grouped checkbox picker for Django auth Permission M2M fields."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django import forms
from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.db.models import QuerySet
from django.utils.text import capfirst

_CODENAME_ORDER = {"view": 0, "add": 1, "change": 2, "delete": 3}
_ACTION_PREFIXES: tuple[tuple[str, str], ...] = (
    ("view_", "Просмотр"),
    ("add_", "Добавление"),
    ("change_", "Изменение"),
    ("delete_", "Удаление"),
)


STANDARD_PERMISSION_BULK_ACTIONS: tuple[tuple[str, str], ...] = tuple(
    (prefix.rstrip("_"), label) for prefix, label in _ACTION_PREFIXES
)


@dataclass(frozen=True, slots=True)
class PermissionRow:
    """One permission checkbox."""

    pk: int
    codename: str
    action_label: str
    action_key: str


@dataclass(frozen=True, slots=True)
class ModelPermissionGroup:
    """Permissions for one model within an app."""

    slug: str
    label: str
    permissions: tuple[PermissionRow, ...]


@dataclass(frozen=True, slots=True)
class AppPermissionGroup:
    """Permissions grouped under an app verbose name."""

    slug: str
    label: str
    models: tuple[ModelPermissionGroup, ...]


def permission_action_key(codename: str) -> str:
    """Stable key for bulk toggles (view/add/change/delete/other)."""
    for prefix, _label in _ACTION_PREFIXES:
        if codename.startswith(prefix):
            return prefix.rstrip("_")
    return "other"


def permission_action_label(codename: str, verbose_name: str) -> str:
    """Short Russian label for standard add/change/delete/view codenames."""
    for prefix, label in _ACTION_PREFIXES:
        if codename.startswith(prefix):
            return label
    if verbose_name.startswith("Can "):
        return verbose_name[4:]
    return verbose_name


def _codename_sort_key(codename: str) -> tuple[int, str]:
    for action, order in _CODENAME_ORDER.items():
        if codename.startswith(f"{action}_"):
            return order, codename
    return 99, codename


def _app_verbose_name(app_label: str) -> str:
    try:
        return str(apps.get_app_config(app_label).verbose_name)
    except LookupError:
        return app_label


_MODEL_SLUG_SPLIT_TOKENS: tuple[str, ...] = (
    "delegation",
    "subscription",
    "conversation",
    "permission",
    "schedule",
    "interval",
    "account",
    "member",
    "state",
    "touch",
    "label",
    "order",
    "item",
)


def _label_looks_like_model_slug(label: str, model_key: str) -> bool:
    compact = label.replace(" ", "").replace("_", "").casefold()
    return compact == model_key.replace("_", "").casefold()


_REGLUED_MODEL_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("leadelegation", "lead delegation"),
    ("delegationstate", "delegation state"),
)


def _humanize_model_slug(model_key: str) -> str:
    """Turn ``leadelegationstate`` into «Lead delegation state» when Meta is missing."""
    text = model_key.replace("_", " ").casefold()
    for glued, spaced in _REGLUED_MODEL_FRAGMENTS:
        text = text.replace(glued, spaced)
    for token in sorted(_MODEL_SLUG_SPLIT_TOKENS, key=len, reverse=True):
        text = re.sub(rf"(?<=[a-z]){re.escape(token)}", f" {token}", text)
    text = re.sub(r"\s+", " ", text).strip()
    return capfirst(text) if text else model_key


def _model_label_from_can_permission(permission_name: str) -> str | None:
    if not permission_name.startswith("Can "):
        return None
    tail = permission_name[4:]
    for verb in ("view ", "add ", "change ", "delete "):
        if tail.casefold().startswith(verb):
            return tail[len(verb) :].strip()
    return tail.strip()


def _resolve_model_label(
    app_label: str,
    model_key: str,
    content_type_name: str,
    permission_names: Iterable[str],
) -> str:
    try:
        model_class = apps.get_model(app_label, model_key)
    except LookupError:
        model_class = None
    if model_class is not None:
        label = str(model_class._meta.verbose_name)
        if not _label_looks_like_model_slug(label, model_key):
            return label
    for permission_name in permission_names:
        inferred = _model_label_from_can_permission(permission_name)
        if inferred and not _label_looks_like_model_slug(inferred, model_key):
            return inferred
    ct_name = (content_type_name or "").strip()
    if ct_name and not _label_looks_like_model_slug(ct_name, model_key):
        return capfirst(ct_name)
    return _humanize_model_slug(model_key)


def build_permission_groups(queryset: Iterable[Permission]) -> tuple[AppPermissionGroup, ...]:
    """Group permissions by app → model for the admin picker."""
    by_app: dict[str, dict[str, list[PermissionRow]]] = {}
    app_labels: dict[str, str] = {}
    model_meta: dict[tuple[str, str], tuple[str, list[str]]] = {}

    for perm in queryset:
        ct = perm.content_type
        app_key = ct.app_label
        model_key = ct.model
        app_labels.setdefault(app_key, _app_verbose_name(app_key))
        meta_key = (app_key, model_key)
        if meta_key not in model_meta:
            model_meta[meta_key] = (ct.name, [])
        model_meta[meta_key][1].append(perm.name)
        model_bucket = by_app.setdefault(app_key, {}).setdefault(model_key, [])
        model_bucket.append(
            PermissionRow(
                pk=perm.pk,
                codename=perm.codename,
                action_label=permission_action_label(perm.codename, perm.name),
                action_key=permission_action_key(perm.codename),
            ),
        )

    app_groups: list[AppPermissionGroup] = []
    for app_key in sorted(by_app, key=lambda key: app_labels[key].casefold()):
        model_groups: list[ModelPermissionGroup] = []
        for model_key in sorted(by_app[app_key]):
            rows = sorted(by_app[app_key][model_key], key=lambda row: _codename_sort_key(row.codename))
            ct_name, permission_names = model_meta[(app_key, model_key)]
            label = _resolve_model_label(app_key, model_key, ct_name, permission_names)
            model_groups.append(
                ModelPermissionGroup(
                    slug=f"{app_key}__{model_key}",
                    label=label,
                    permissions=tuple(rows),
                ),
            )
        app_groups.append(
            AppPermissionGroup(
                slug=app_key,
                label=app_labels[app_key],
                models=tuple(model_groups),
            ),
        )
    return tuple(app_groups)


class GroupedPermissionWidget(forms.Widget):
    """Checkboxes by app and model instead of filter_horizontal dual lists.

    Template path: ``accounts/templates/admin/widgets/grouped_permissions.html``
    (Django's default form renderer does not read ``settings.TEMPLATES`` DIRS).
    """

    template_name = "admin/widgets/grouped_permissions.html"
    allow_multiple_selected = True

    class Media:
        js = ("admin/js/hoocon-admin-permissions.js",)

    def __init__(self, attrs: dict[str, Any] | None = None, *, queryset: QuerySet[Permission] | None = None) -> None:
        self.queryset = queryset
        super().__init__(attrs)

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        selected: set[str] = set()
        if value:
            selected = {str(item) for item in value}
        qs = self.queryset if self.queryset is not None else Permission.objects.none()
        context["permission_groups"] = build_permission_groups(qs)
        context["selected_ids"] = selected
        context["standard_bulk_actions"] = STANDARD_PERMISSION_BULK_ACTIONS
        return context

    def value_from_datadict(self, data: Any, files: Any, name: str) -> list[str]:
        del files
        if hasattr(data, "getlist"):
            return data.getlist(name)
        raw = data.get(name)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return [raw]


def ordered_permission_queryset() -> QuerySet[Permission]:
    """Default ordering for auth permission pickers."""
    return Permission.objects.select_related("content_type").order_by(
        "content_type__app_label",
        "content_type__model",
        "codename",
    )


class AuthGroupCheckboxWidget(forms.Widget):
    """Staff groups on User — checkboxes instead of filter_horizontal."""

    template_name = "admin/widgets/auth_groups_checkbox.html"
    allow_multiple_selected = True

    def __init__(self, attrs: dict[str, Any] | None = None, *, queryset: QuerySet[Group] | None = None) -> None:
        self.queryset = queryset
        super().__init__(attrs)

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        selected: set[str] = set()
        if value:
            selected = {str(item) for item in value}
        qs = self.queryset if self.queryset is not None else Group.objects.none()
        context["groups"] = qs.order_by("name")
        context["selected_ids"] = selected
        return context

    def value_from_datadict(self, data: Any, files: Any, name: str) -> list[str]:
        del files
        if hasattr(data, "getlist"):
            return data.getlist(name)
        raw = data.get(name)
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return [raw]


def install_admin_permission_pickers() -> None:
    """Replace filter_horizontal Permission/Group pickers across all ModelAdmins."""
    from django.contrib.admin.options import BaseModelAdmin

    current = BaseModelAdmin.formfield_for_manytomany
    if getattr(current, "_hoocon_permission_pickers", False):
        return

    def formfield_for_manytomany(self: Any, db_field: Any, request: Any, **kwargs: Any) -> Any:
        field = current(self, db_field, request, **kwargs)
        if field is None:
            return field
        remote = db_field.remote_field.model
        if remote is Permission and db_field.name in ("permissions", "user_permissions"):
            if field.queryset is None:
                field.queryset = ordered_permission_queryset()
            field.widget = GroupedPermissionWidget(queryset=field.queryset)
        elif remote is Group and db_field.name == "groups":
            if field.queryset is None:
                field.queryset = Group.objects.order_by("name")
            field.widget = AuthGroupCheckboxWidget(queryset=field.queryset)
        elif db_field.name == "work_labels":
            from crm.models import WorkLabel
            from crm.work_label_widget import WorkLabelGroupedWidget, assignable_work_label_queryset

            if remote is WorkLabel:
                field.queryset = assignable_work_label_queryset(field.queryset)
                field.widget = WorkLabelGroupedWidget(queryset=field.queryset)
        return field

    formfield_for_manytomany._hoocon_permission_pickers = True  # type: ignore[attr-defined]
    BaseModelAdmin.formfield_for_manytomany = formfield_for_manytomany  # type: ignore[method-assign]
