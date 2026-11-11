"""Replay a rendered admin change form in tests."""

from __future__ import annotations

from typing import Any

from django.test import Client


def _put_admin_value(data: dict[str, Any], key: str, value: Any) -> None:
    """Copy one admin field into a POST body. An unchecked box stays absent."""
    if value is None or value is False:
        return
    if value is True:
        data[key] = "on"
        return
    if isinstance(value, list | tuple):
        data[key] = ["" if item is None else str(item) for item in value]
        return
    data[key] = str(value)


def _put_bound_field(data: dict[str, Any], bound: Any) -> None:
    """Copy a bound field, including split date widgets, into the POST body."""
    widget = bound.field.widget
    value = bound.value()
    if hasattr(widget, "decompress"):
        parts = widget.decompress(value)
        for index, part in enumerate(parts):
            _put_admin_value(data, f"{bound.html_name}_{index}", part)
        return
    _put_admin_value(data, bound.html_name, value)


def _admin_change_post(page: Client, url: str) -> dict[str, Any]:
    """Replay the rendered change form so a tampered inline is the only delta."""
    response = page.get(url)
    assert response.status_code == 200, response.status_code
    data: dict[str, Any] = {}
    for fieldset in response.context["adminform"]:
        for line in fieldset:
            for admin_field in line:
                if getattr(admin_field, "is_readonly", False):
                    continue
                _put_bound_field(data, admin_field.field)
    for formset in response.context["inline_admin_formsets"]:
        forms = formset.formset
        data[f"{forms.prefix}-TOTAL_FORMS"] = str(forms.total_form_count())
        data[f"{forms.prefix}-INITIAL_FORMS"] = str(forms.initial_form_count())
        data[f"{forms.prefix}-MIN_NUM_FORMS"] = str(forms.min_num)
        data[f"{forms.prefix}-MAX_NUM_FORMS"] = str(forms.max_num)
        for form in forms.forms:
            for name in form.fields:
                _put_bound_field(data, form[name])
    return data
