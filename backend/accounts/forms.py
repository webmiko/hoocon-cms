"""Staff User Admin forms: login = email, display name = first_name."""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminEmailInputWidget, UnfoldAdminTextInputWidget


def admin_email_otp_enabled() -> bool:
    """True when Admin login uses one-time codes emailed to staff."""
    return bool(getattr(settings, "ADMIN_EMAIL_OTP_ENABLED", False))


class StaffUserCreationForm(AdminUserCreationForm):
    """Create staff with email as login and a display name for lead emails.

    When ``ADMIN_EMAIL_OTP_ENABLED``, passwords are skipped: login is a
    one-time code to the same email. Otherwise password fields stay available.
    """

    email = forms.EmailField(
        label="Логин (эл. почта)",
        required=True,
        widget=UnfoldAdminEmailInputWidget(),
        help_text=(
            "Вход в админку и уведомления о заявках идут на этот адрес. Одноразовый код для входа приходит сюда же."
        ),
    )
    first_name = forms.CharField(
        label="Имя для отображения",
        required=True,
        max_length=150,
        widget=UnfoldAdminTextInputWidget(),
        help_text="Так менеджер будет подписан в письмах о назначенных заявках.",
    )

    class Meta(AdminUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name")

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Drop username; for OTP mode hide passwords and force unusable."""
        super().__init__(*args, **kwargs)
        self.fields.pop("username", None)
        if admin_email_otp_enabled():
            self.fields.pop("password1", None)
            self.fields.pop("password2", None)
            self.fields.pop("usable_password", None)
        elif "usable_password" in self.fields:
            self.fields["usable_password"].label = "Вход по постоянному паролю"
            self.fields[
                "usable_password"
            ].help_text = "Если выкл. — пароль не задаётся (удобно, когда вход только по одноразовому коду на почту)."
            self.fields["usable_password"].choices = [
                ("true", "Задать пароль"),
                ("false", "Без пароля (код на почту)"),
            ]

    def validate_passwords(self, *args: object, **kwargs: object) -> None:
        """OTP mode: skip password checks; permanent password is not used."""
        if admin_email_otp_enabled():
            self.cleaned_data["set_usable_password"] = False
            return
        super().validate_passwords(*args, **kwargs)  # type: ignore[misc]

    def clean_email(self) -> str:
        """Normalize email; reject duplicates on username or email."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError(_("Введите адрес эл. почты."), code="required")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                _("Пользователь с такой почтой уже есть."),
                code="duplicate_email",
            )
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError(
                _("Пользователь с таким логином уже есть."),
                code="duplicate_username",
            )
        return email

    def clean_first_name(self) -> str:
        """Require a non-empty display name."""
        name = (self.cleaned_data.get("first_name") or "").strip()
        if not name:
            raise ValidationError(_("Укажите имя для отображения."), code="required")
        return name

    def save(self, commit: bool = True) -> User:
        """Persist user with username == email."""
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        user.username = email
        user.email = email
        user.first_name = self.cleaned_data["first_name"]
        if admin_email_otp_enabled():
            user.set_unusable_password()
        if commit:
            user.save()
            if hasattr(self, "save_m2m"):
                self.save_m2m()
        return user


class StaffUserChangeForm(UserChangeForm):
    """Edit staff: keep login email and display name prominent."""

    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Russian labels for email / first_name; Unfold widgets; email required."""
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].label = "Логин (эл. почта)"
        self.fields["email"].widget = UnfoldAdminEmailInputWidget()
        self.fields[
            "email"
        ].help_text = (
            "Совпадает с логином. Вход в админку — одноразовый код на эту почту; сюда же уходят письма о заявках."
        )
        self.fields["first_name"].required = True
        self.fields["first_name"].label = "Имя для отображения"
        self.fields["first_name"].widget = UnfoldAdminTextInputWidget()
        self.fields["first_name"].help_text = "Подпись менеджера в письмах о назначенных заявках."
        if "username" in self.fields:
            self.fields["username"].help_text = "Служебное поле: при сохранении подставляется из почты."
        if "password" in self.fields and admin_email_otp_enabled():
            self.fields[
                "password"
            ].help_text = "Вход в админку — одноразовым кодом на почту. Постоянный пароль обычно не нужен."

    def clean_email(self) -> str:
        """Normalize email; unique among other users."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError(_("Введите адрес эл. почты."), code="required")
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                _("Пользователь с такой почтой уже есть."),
                code="duplicate_email",
            )
        return email

    def clean_first_name(self) -> str:
        """Require a non-empty display name."""
        name = (self.cleaned_data.get("first_name") or "").strip()
        if not name:
            raise ValidationError(_("Укажите имя для отображения."), code="required")
        return name

    def save(self, commit: bool = True) -> User:
        """Keep username in sync with email."""
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        user.email = email
        user.username = email
        user.first_name = self.cleaned_data["first_name"]
        if commit:
            user.save()
            self.save_m2m()
        return user
