"""Work label M2M on company/lead: active-only choices, keep inactive already on card."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from crm.models import WorkLabel
from crm.work_label_widget import WorkLabelGroupedWidget


class WorkLabelAssignableFormMixin:
    """Allow saving a card that still has legacy inactive marks; block new inactive picks."""

    def get_form(self, request: HttpRequest, obj: Any = None, **kwargs: Any) -> type:
        form_class = super().get_form(request, obj, **kwargs)  # type: ignore[misc]

        class Form(form_class):  # type: ignore[misc,valid-type]
            def __init__(self, *args: Any, **kw: Any) -> None:
                super().__init__(*args, **kw)
                field = self.fields.get("work_labels")
                if field is None or obj is None or not getattr(obj, "pk", None):
                    return
                legacy = obj.work_labels.filter(is_active=False)
                if not legacy.exists():
                    return
                merged = field.queryset | WorkLabel.objects.filter(pk__in=legacy.values_list("pk", flat=True))
                field.queryset = merged.distinct().order_by("sort", "name")
                if isinstance(field.widget, WorkLabelGroupedWidget):
                    field.widget.queryset = field.queryset

        Form.__name__ = form_class.__name__
        return Form
