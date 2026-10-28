"""Work labels on Company / Lead — grouped checkboxes instead of dual lists."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django import forms
from django.db.models import QuerySet

from crm.models import WorkLabel


def assignable_work_label_queryset(queryset: QuerySet[WorkLabel] | None = None) -> QuerySet[WorkLabel]:
    """Choices for assign: active catalog rows only (server-side, matches default UI)."""
    base = queryset if queryset is not None else WorkLabel.objects.all()
    return base.filter(is_active=True).order_by("sort", "name")


@dataclass(frozen=True, slots=True)
class WorkLabelRow:
    pk: int
    name: str
    code: str


@dataclass(frozen=True, slots=True)
class WorkLabelGroup:
    slug: str
    label: str
    labels: tuple[WorkLabelRow, ...]


def build_work_label_groups(queryset: Iterable[WorkLabel]) -> tuple[WorkLabelGroup, ...]:
    """Group active work labels by ``kind`` (очередь / флаг / сегмент)."""
    buckets: dict[str, list[WorkLabelRow]] = {key: [] for key, _ in WorkLabel.Kind.choices}
    for label in queryset:
        if label.kind not in buckets:
            continue
        buckets[label.kind].append(WorkLabelRow(pk=label.pk, name=label.name, code=label.code))
    groups: list[WorkLabelGroup] = []
    for kind, title in WorkLabel.Kind.choices:
        rows = sorted(buckets[kind], key=lambda row: row.name.casefold())
        if not rows:
            continue
        groups.append(WorkLabelGroup(slug=kind, label=str(title), labels=tuple(rows)))
    return tuple(groups)


class WorkLabelGroupedWidget(forms.Widget):
    """Checkboxes by label kind (queue / flag / segment)."""

    template_name = "admin/crm/widgets/grouped_work_labels.html"
    allow_multiple_selected = True

    class Media:
        js = ("admin/js/hoocon-admin-permissions.js",)

    def __init__(self, attrs: dict[str, Any] | None = None, *, queryset: QuerySet[WorkLabel] | None = None) -> None:
        self.queryset = queryset
        super().__init__(attrs)

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        selected: set[str] = set()
        if value:
            selected = {str(item) for item in value}
        base = self.queryset if self.queryset is not None else WorkLabel.objects.none()
        selected_pks: list[int] = []
        for raw_pk in selected:
            try:
                selected_pks.append(int(raw_pk))
            except (TypeError, ValueError):
                continue
        qs = base
        if selected_pks:
            legacy = WorkLabel.objects.filter(pk__in=selected_pks, is_active=False)
            if legacy.exists():
                qs = (base | legacy).distinct().order_by("sort", "name")
        else:
            qs = base.order_by("sort", "name")
        context["label_groups"] = build_work_label_groups(qs)
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
