"""Boolean fields in Admin render as the integrations toggle.

A checkmark stays only where a switch does not fit: picking rows, deleting an
inline, choosing many permissions, and a one-off action such as «delete token».
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.html import format_html
from django.utils.safestring import SafeString

# Field name (without the inline prefix) → (off, on).
_LABELS: dict[str, tuple[str, str]] = {
    "smtp_use_ssl": ("STARTTLS", "SSL"),
    "send_now": ("Черновик", "Отправить сразу"),
}
_DEFAULT = ("Выключено", "Включено")


class HooconToggleInput(forms.CheckboxInput):
    """Switch plus a caption that follows the checked state."""

    def __init__(self, attrs: dict[str, Any] | None = None, check_test: Any = None) -> None:
        merged = {"class": "hoocon-toggle"}
        if attrs:
            extra = attrs.get("class")
            merged.update(attrs)
            if extra:
                merged["class"] = f"hoocon-toggle {extra}".strip()
        super().__init__(merged, check_test)

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:
        context = super().get_context(name, value, attrs)
        key = (name or "").rsplit("-", 1)[-1]
        label_off, label_on = _LABELS.get(key, _DEFAULT)
        context["label_off"] = label_off
        context["label_on"] = label_on
        return context

    def render(self, name: str, value: Any, attrs: dict[str, Any] | None = None, renderer: Any = None) -> SafeString:
        context = self.get_context(name, value, attrs)
        return format_html(
            '<label class="hoocon-bool-toggle">{}'
            '<span class="hoocon-bool-toggle__state hoocon-bool-toggle__state--off">{}</span>'
            '<span class="hoocon-bool-toggle__state hoocon-bool-toggle__state--on">{}</span>'
            "</label>",
            super().render(name, value, attrs, renderer),
            context["label_off"],
            context["label_on"],
        )


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

    FORMFIELD_OVERRIDES[models.BooleanField] = {"widget": HooconToggleInput}
    FORMFIELD_OVERRIDES_INLINE[models.BooleanField] = {"widget": HooconToggleInput}
    for model_admin in admin.site._registry.values():
        overrides = model_admin.formfield_overrides
        current = overrides.get(models.BooleanField)
        if isinstance(current, dict) and current.get("widget") is HooconToggleInput:
            continue
        merged = dict(current) if isinstance(current, dict) else {}
        merged["widget"] = HooconToggleInput
        # Instance attribute, not the shared ModelAdmin class dict.
        model_admin.__dict__["formfield_overrides"] = {**overrides, models.BooleanField: merged}
