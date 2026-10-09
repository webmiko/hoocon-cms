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
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import ActionForm

from accounts.forms import StaffMailboxForm, StaffUserChangeForm, StaffUserCreationForm
from accounts.models import (
    ClientAccount,
    PasskeyCredential,
    SocialAccount,
    StaffMailbox,
    StaffMaxProfile,
    StaffTelegramProfile,
    StaffVpbxProfile,
)
from accounts.passkeys import admin_passkey_enabled
from accounts.recovery_codes import replace_recovery_codes, unused_recovery_code_count
from config.admin_mixins import OpenChangeLinkMixin


class StaffTelegramProfileInline(admin.StackedInline):
    """Personal Telegram chat id for staff alerts."""

    model = StaffTelegramProfile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ("telegram_chat_id", "telegram_alerts_enabled")
    verbose_name = "Telegram"
    verbose_name_plural = "Telegram сотрудника"


class StaffMaxProfileInline(admin.StackedInline):
    """Personal MAX user_id for staff alerts."""

    model = StaffMaxProfile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ("max_user_id", "max_alerts_enabled")
    verbose_name = "MAX"
    verbose_name_plural = "MAX сотрудника"


class StaffMailboxInline(admin.StackedInline):
    """Personal IMAP mailbox: CRM-mail fetch source for this manager."""

    model = StaffMailbox
    form = StaffMailboxForm
    can_delete = False
    extra = 1
    max_num = 1
    fields = (
        "imap_user",
        "imap_password",
        "folder",
        "smtp_host",
        "smtp_port",
        "smtp_use_ssl",
        "is_enabled",
        "last_uid",
        "last_run_at",
        "last_error",
    )
    readonly_fields = ("last_uid", "last_run_at", "last_error")
    verbose_name = "Почта (IMAP/SMTP)"
    verbose_name_plural = "Почта менеджера (IMAP/SMTP)"


class StaffVpbxProfileInline(admin.StackedInline):
    """Mango VPBX extension — binds inbound/outbound calls to this manager."""

    model = StaffVpbxProfile
    can_delete = False
    extra = 1
    max_num = 1
    fields = ("extension", "uis_employee_id", "is_enabled")
    verbose_name = "Телефония сотрудника"
    verbose_name_plural = "Телефония сотрудника"


class UserAdmin(BaseUserAdmin, ModelAdmin):
    """Staff users — login email, display name, Unfold Add button."""

    action_form = ActionForm
    # Unfold add_link.html gates on this; Django UserAdmin alone omits the button.
    show_add_link = True
    form = StaffUserChangeForm
    add_form = StaffUserCreationForm
    inlines = (
        StaffTelegramProfileInline,
        StaffMaxProfileInline,
        StaffMailboxInline,
        StaffVpbxProfileInline,
    )
    list_display = (
        "email",
        "first_name",
        "is_staff",
        "is_active",
        "is_superuser",
        "telegram_chat_short",
        "max_user_short",
        "mailbox_short",
    )
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

    @admin.display(description="Telegram")
    def telegram_chat_short(self, obj: User) -> str:
        """Show linked chat id on the user list."""
        profile = getattr(obj, "telegram_profile", None)
        if profile is None:
            return "—"
        chat = (profile.telegram_chat_id or "").strip()
        if not chat:
            return "—"
        if not profile.telegram_alerts_enabled:
            return f"{chat} (выкл)"
        return chat

    @admin.display(description="MAX")
    def max_user_short(self, obj: User) -> str:
        """Show linked MAX user id on the user list."""
        profile = getattr(obj, "max_profile", None)
        if profile is None:
            return "—"
        uid = (profile.max_user_id or "").strip()
        if not uid:
            return "—"
        if not profile.max_alerts_enabled:
            return f"{uid} (выкл)"
        return uid

    @admin.display(description="Почта (IMAP)")
    def mailbox_short(self, obj: User) -> str:
        """Show configured mailbox on the user list."""
        mailbox = getattr(obj, "mailbox", None)
        if mailbox is None:
            return "—"
        addr = (mailbox.imap_user or "").strip()
        if not addr:
            return "—"
        if not mailbox.is_enabled:
            return f"{addr} (выкл)"
        return addr

    def get_queryset(self, request: HttpRequest) -> Any:
        return (
            super()
            .get_queryset(request)
            .select_related(
                "telegram_profile",
                "max_profile",
                "mailbox",
            )
        )

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

    def get_queryset(self, request: HttpRequest) -> Any:
        return super().get_queryset(request).select_related("user")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_module_permission(self, request: HttpRequest) -> bool:
        return admin_passkey_enabled() and super().has_module_permission(request)


class SocialAccountInline(TabularInline):
    """OAuth привязки аккаунта (задел под Яндекс ID)."""

    model = SocialAccount
    extra = 0
    fields = ("provider", "provider_user_id", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(ClientAccount)
class ClientAccountAdmin(OpenChangeLinkMixin, ModelAdmin):
    """Аккаунты личного кабинета клиентов (read-mostly; пароль — только хеш)."""

    list_display = ("email", "name", "auth_mode", "is_active", "email_verified_at", "created_at")
    list_display_links = ("email",)
    list_filter = ("auth_mode", "is_active")
    search_fields = ("email", "name", "phone")
    readonly_fields = (
        "password_hash",
        "email_verified_at",
        "pdn_consent_at",
        "pdn_policy_version",
        "created_at",
        "updated_at",
    )
    inlines = (SocialAccountInline,)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Аккаунты создаются через публичную регистрацию."""
        return False
