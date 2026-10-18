"""Boolean fields in Admin render as the integrations toggle.

A checkmark stays only where a switch does not fit: picking rows, deleting an
inline, choosing many permissions, and a one-off action such as «delete token».
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.safestring import SafeString

_DEFAULT = ("Выключено", "Включено")


class HooconToggleInput(forms.CheckboxInput):
    """Switch plus a caption that follows the checked state.

    ``labels`` is ``(off, on)``; pass it where the default captions mislead.
    """

    def __init__(
        self,
        attrs: dict[str, Any] | None = None,
        check_test: Any = None,
        labels: tuple[str, str] = _DEFAULT,
    ) -> None:
        self.labels = labels
        merged = {"class": "hoocon-toggle"}
        if attrs:
            extra = attrs.get("class")
            merged.update(attrs)
            if extra:
                merged["class"] = f"hoocon-toggle {extra}".strip()
        super().__init__(merged, check_test)

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> SafeString:
        label_off, label_on = self.labels
        return format_html(
            '<label class="hoocon-bool-toggle">{}'
            '<span class="hoocon-bool-toggle__state hoocon-bool-toggle__state--off">{}</span>'
            '<span class="hoocon-bool-toggle__state hoocon-bool-toggle__state--on">{}</span>'
            "</label>",
            super().render(name, value, attrs, renderer),
            label_off,
            label_on,
        )


class ToggleBooleanField(forms.BooleanField):
    """Admin boolean whose switch is named by the field label.

    The caption next to the switch changes with its position, and in tabular
    inlines the field name sits in the column header, so the label goes to
    ``aria-label`` for every toggle, not only the captioned ones.
    """

    def widget_attrs(self, widget: forms.Widget) -> dict[str, Any]:
        attrs = super().widget_attrs(widget)
        if isinstance(widget, HooconToggleInput) and self.label and "aria-label" not in widget.attrs:
            attrs["aria-label"] = str(self.label)
        return attrs


_OVERRIDE: dict[str, Any] = {"widget": HooconToggleInput, "form_class": ToggleBooleanField}


def install_admin_boolean_toggles() -> None:
    """Use the toggle for every Admin boolean, including inlines.

    ``django.contrib.admin`` autodiscover runs before this app's ``ready``.
    Each ``ModelAdmin`` has already copied ``FORMFIELD_OVERRIDES``, so the
    source dict is not enough: the live copies on the registry need the same
    widget.
    """
    from django.contrib import admin
    from django.db import models
    from unfold.overrides import FORMFIELD_OVERRIDES, FORMFIELD_OVERRIDES_INLINE

    FORMFIELD_OVERRIDES[models.BooleanField] = dict(_OVERRIDE)
    FORMFIELD_OVERRIDES_INLINE[models.BooleanField] = dict(_OVERRIDE)
    for model_admin in admin.site._registry.values():
        overrides = model_admin.formfield_overrides
        current = overrides.get(models.BooleanField)
        if isinstance(current, dict) and all(current.get(key) is value for key, value in _OVERRIDE.items()):
            continue
        merged = {**(current if isinstance(current, dict) else {}), **_OVERRIDE}
        # Instance attribute, not the shared ModelAdmin class dict.
        model_admin.__dict__["formfield_overrides"] = {**overrides, models.BooleanField: merged}


class LabeledToggleMixin:
    """Per-field captions for the boolean switch on admins and inlines.

    The global override gives every ``BooleanField`` the default
    «Выключено / Включено» pair. Fields whose flag is a state rather than
    on/off get meaningful captions through ``toggle_labels`` —
    ``{"field_name": ("off caption", "on caption")}``.

    Works on ``ModelAdmin`` and ``InlineModelAdmin``: both build widgets
    through ``formfield_for_dbfield``. ``aria-label`` comes from
    ``ToggleBooleanField`` for every toggle, captioned or not.
    """

    toggle_labels: dict[str, tuple[str, str]] = {}

    def formfield_for_dbfield(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)  # type: ignore[misc]
        labels = self.toggle_labels.get(getattr(db_field, "name", ""))
        if labels is not None and formfield is not None and isinstance(formfield.widget, HooconToggleInput):
            formfield.widget.labels = labels
        return formfield
