"""Auth admin: Unfold-compatible User/Group (Add button + ActionForm).

Superuser break-glass: generate one-time recovery codes (shown once).
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.forms import ActionForm

from accounts.forms import StaffUserChangeForm, StaffUserCreationForm
from accounts.models import PasskeyCredential
from accounts.passkeys import admin_passkey_enabled
from accounts.recovery_codes import replace_recovery_codes, unused_recovery_code_count


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
        (
            "Аварийный вход",
            {
                "fields": ("recovery_codes_summary",),
                "description": (
                    "Резервные одноразовые коды только для супер-админа: "
                    "если нет почты и забыт постоянный пароль. "
                    "Новая генерация аннулирует старые коды."
                ),
            },
        ),
        (
            "Ключи доступа",
            {
                "fields": ("passkeys_summary",),
                "description": (
                    "Passkey (Связка ключей / Google Password Manager) — "
                    "вход в админку без пароля. Включается флагом "
                    "ADMIN_PASSKEY_ENABLED."
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
    readonly_fields = (
        "username",
        "last_login",
        "date_joined",
        "recovery_codes_summary",
        "passkeys_summary",
    )

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
        fieldsets: tuple = self.fieldsets
        if not obj.is_superuser or not request.user.is_superuser:
            # Hide recovery fieldset for non-superuser targets/viewers.
            fieldsets = tuple(fs for fs in fieldsets if fs[0] != "Аварийный вход")
        if not admin_passkey_enabled():
            fieldsets = tuple(fs for fs in fieldsets if fs[0] != "Ключи доступа")
        return fieldsets

    def get_readonly_fields(self, request: HttpRequest, obj: User | None = None) -> tuple:
        base = super().get_readonly_fields(request, obj)
        extra = ("recovery_codes_summary", "passkeys_summary")
        out = tuple(base)
        for name in extra:
            if name not in out:
                out = (*out, name)
        return out

    @admin.display(description="Резервные коды")
    def recovery_codes_summary(self, obj: User) -> str:
        """Unused count + generate button (HTML for change form)."""
        if not obj.pk or not obj.is_superuser:
            return "—"
        unused = unused_recovery_code_count(obj)
        url = reverse("admin:auth_user_generate_recovery_codes", args=[obj.pk])
        return format_html(
            '<p class="mb-2">Неиспользованных кодов: <strong>{}</strong></p>'
            '<a class="button" href="{}">Сгенерировать новые коды</a>'
            '<p class="help mt-2">Старые коды будут аннулированы. '
            "Текст кодов покажется один раз.</p>",
            unused,
            url,
        )

    @admin.display(description="Ключи доступа")
    def passkeys_summary(self, obj: User) -> str:
        """Count + link to manage page."""
        if not obj.pk or not admin_passkey_enabled():
            return "—"
        count = PasskeyCredential.objects.filter(user=obj).count()
        url = reverse("admin:passkey_manage")
        if obj.pk:
            url = f"{url}?user={obj.pk}"
        return format_html(
            '<p class="mb-2">Зарегистрировано ключей: <strong>{}</strong></p>'
            '<a class="button" href="{}">Управлять ключами доступа</a>',
            count,
            url,
        )

    def get_urls(self) -> list:
        urls = super().get_urls()
        custom = [
            path(
                "<id>/generate-recovery-codes/",
                self.admin_site.admin_view(self.generate_recovery_codes_view),
                name="auth_user_generate_recovery_codes",
            ),
        ]
        return custom + urls

    def generate_recovery_codes_view(
        self,
        request: HttpRequest,
        id: str,  # noqa: A002 — Django admin URL kwarg
    ) -> HttpResponse:
        """POST generates codes; GET confirms. Superuser-only."""
        if not request.user.is_superuser:
            raise PermissionDenied("Только супер-админ.")
        if not self.has_change_permission(request):
            raise PermissionDenied
        target = get_object_or_404(User, pk=id)
        if not self.has_change_permission(request, target):
            raise PermissionDenied
        if not target.is_superuser:
            messages.error(request, "Резервные коды доступны только супер-админам.")
            return HttpResponseRedirect(
                reverse("admin:auth_user_change", args=[target.pk]),
            )

        if request.method == "POST":
            codes = replace_recovery_codes(target)
            context = {
                **self.admin_site.each_context(request),
                "title": "Резервные коды",
                "recovery_codes": codes,
                "target_user": target,
                "back_url": reverse("admin:auth_user_change", args=[target.pk]),
                "opts": self.model._meta,
                "has_permission": True,
            }
            return render(request, "admin/recovery_codes_once.html", context)

        context = {
            **self.admin_site.each_context(request),
            "title": "Сгенерировать резервные коды",
            "target_user": target,
            "unused_count": unused_recovery_code_count(target),
            "back_url": reverse("admin:auth_user_change", args=[target.pk]),
            "opts": self.model._meta,
            "has_permission": True,
        }
        return render(request, "admin/recovery_codes_confirm.html", context)

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


@admin.register(PasskeyCredential)
class PasskeyCredentialAdmin(ModelAdmin):
    """Read-mostly list of registered Admin passkeys."""

    action_form = ActionForm
    list_display = ("device_name", "user", "created_at", "last_used_at", "sign_count")
    list_filter = ("created_at",)
    search_fields = ("device_name", "user__email", "user__username", "credential_id")
    readonly_fields = (
        "user",
        "credential_id",
        "sign_count",
        "created_at",
        "last_used_at",
    )
    fields = (
        "user",
        "device_name",
        "credential_id",
        "sign_count",
        "created_at",
        "last_used_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_module_permission(self, request: HttpRequest) -> bool:
        return admin_passkey_enabled() and super().has_module_permission(request)
