"""Unfold ActionForm on auth User/Group changelist."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.models import Group, User
from unfold.forms import ActionForm


def test_user_and_group_admin_use_unfold_action_form() -> None:
    assert admin.site._registry[User].action_form is ActionForm
    assert admin.site._registry[Group].action_form is ActionForm
    form = ActionForm(auto_id=None)
    form.fields["action"].choices = [("", "---"), ("delete_selected", "del")]
    assert form.fields["action"].widget.attrs.get("x-model") == "action"
