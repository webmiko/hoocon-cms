"""Auth admin: Unfold-compatible action form (Run button on changelist)."""

from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.forms import ActionForm


class UserAdmin(BaseUserAdmin):
    """Staff users — Unfold ActionForm so Alpine shows the Run button."""

    action_form = ActionForm


class GroupAdmin(BaseGroupAdmin):
    """Auth groups — same Unfold ActionForm as UserAdmin."""

    action_form = ActionForm


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, UserAdmin)
admin.site.register(Group, GroupAdmin)
