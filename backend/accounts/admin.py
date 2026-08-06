"""Auth admin: Unfold-compatible User/Group (Add button + ActionForm)."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.http import HttpRequest
from unfold.admin import ModelAdmin
from unfold.forms import ActionForm

from accounts.forms import StaffUserChangeForm, StaffUserCreationForm


class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Staff users — login email, display name, Unfold Add button."""

    action_form = ActionForm
    # Unfold add_link.html gates on this; Django UserAdmin alone omits the button.
    show_add_link = True
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    list_display = ("email", "first_name", "is_staff", "is_active", "is_superuser")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("email", "first_name", "username", "last_name")
    ordering = ("email",)

    fieldsets = (
        (
            None,
            {
                "fields": ("email", "password"),
                "description": (
                    "Логин — адрес эл. почты (совпадает со служебным логином). Имя для отображения задаётся ниже."
                ),
            },
        ),
        (
            "Личные данные",
            {
                "fields": ("first_name", "last_name"),
                "description": ("«Имя для отображения» попадает в письма о заявках (кто из менеджеров назначен)."),
            },
        ),
        (
            "Права доступа",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Важные даты", {"fields": ("last_login", "date_joined")}),
        (
            "Служебное",
            {
                "classes": ("collapse",),
                "fields": ("username",),
                "description": "Служебный логин синхронизируется с почтой при сохранении.",
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "usable_password", "password1", "password2"),
                "description": (
                    "Логин = эл. почта. Имя для отображения — подпись менеджера "
                    "в письмах о назначенных заявках. Для группы «Менеджер» "
                    "включите «статус персонала» на следующем шаге."
                ),
            },
        ),
    )
    readonly_fields = ("username", "last_login", "date_joined")

    def get_fieldsets(self, request: HttpRequest, obj: User | None = None) -> tuple:
        """On add with OTP: only email + display name (no password fields)."""
        if obj is None:
            from accounts.forms import admin_email_otp_enabled

            if admin_email_otp_enabled():
                return (
                    (
                        None,
                        {
                            "classes": ("wide",),
                            "fields": ("email", "first_name"),
                            "description": (
                                "Логин = эл. почта. Вход — одноразовым кодом на "
                                "эту почту (постоянный пароль не задаётся). "
                                "Имя для отображения — в письмах о заявках. "
                                "Для группы «Менеджер» включите «статус "
                                "персонала» на следующем шаге."
                            ),
                        },
                    ),
                )
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    def save_model(
        self,
        request: HttpRequest,
        obj: User,
        form: Any,
        change: bool,
    ) -> None:
        """Ensure username stays equal to normalized email."""
        email = (obj.email or "").strip().lower()
        if email:
            obj.email = email
            obj.username = email
        super().save_model(request, obj, form, change)


class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    """Auth groups — same Unfold ActionForm / Add button as UserAdmin."""

    action_form = ActionForm
    show_add_link = True


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, UserAdmin)
admin.site.register(Group, GroupAdmin)
