"""Staff User Admin forms: login = email, display name = first_name."""

from __future__ import annotations

from typing import Any

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from unfold.widgets import UnfoldAdminEmailInputWidget, UnfoldAdminTextInputWidget

from accounts.models import StaffMailbox, StaffVpbxProfile


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
            usable_password = self.fields["usable_password"]
            assert isinstance(usable_password, forms.ChoiceField)
            usable_password.choices = [
                ("true", "Задать пароль"),
                ("false", "Без пароля (код на почту)"),
            ]

    def validate_passwords(
        self,
        password1_field_name: str = "password1",
        password2_field_name: str = "password2",
        usable_password_field_name: str = "usable_password",
    ) -> None:
        """OTP mode: skip password checks; permanent password is not used."""
        if admin_email_otp_enabled():
            self.cleaned_data["set_usable_password"] = False
            return
        super().validate_passwords(password1_field_name, password2_field_name, usable_password_field_name)  # type: ignore[misc]

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
            instance = getattr(self, "instance", None)
            if instance is not None and getattr(instance, "is_superuser", False):
                self.fields["password"].help_text = (
                    "Обычный вход — одноразовый код на почту. "
                    "Постоянный пароль — аварийный вход супер-админа, "
                    "если письмо с кодом не доходит "
                    "(ссылка «войти паролем» на экране входа)."
                )
            else:
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


class StaffMailboxForm(forms.ModelForm):
    """Mailbox inline: password masked; empty input keeps the stored one."""

    class Meta:
        model = StaffMailbox
        fields = "__all__"
        widgets = {
            "imap_password": forms.PasswordInput(render_value=False),
        }

    def clean_imap_password(self) -> str:
        """Keep the stored password when the field is submitted empty."""
        value = (self.cleaned_data.get("imap_password") or "").strip()
        if not value and self.instance.pk:
            return self.instance.imap_password
        return value


class StaffVpbxProfileForm(forms.ModelForm):
    """Telephony inline: the WebRTC token is write-only.

    The stored value is a Fernet token and is never rendered back. An empty
    field keeps the saved token; the checkbox removes it. Typing a new token
    and ticking the checkbox together is rejected as ambiguous.
    """

    uis_webrtc_token = forms.CharField(
        label="Токен WebRTC (UIS)",
        required=False,
        max_length=500,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
    )
    clear_uis_webrtc_token = forms.BooleanField(
        label="Удалить токен WebRTC",
        required=False,
        help_text="Телефон в браузере у этого сотрудника перестанет работать.",
    )

    class Meta:
        model = StaffVpbxProfile
        fields = ("extension", "uis_employee_id", "is_enabled", "uis_webrtc_token")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Show whether a token is stored, never the token itself."""
        super().__init__(*args, **kwargs)
        field = self.fields["uis_webrtc_token"]
        state = "сохранён" if self.instance.pk and self.instance.uis_webrtc_token else "не задан"
        field.help_text = f"Токен WebRTC из кабинета UIS. Сейчас: {state}. Пустое поле оставляет сохранённый."

    def clean_uis_employee_id(self) -> str:
        """One UIS employee id belongs to one staff profile; blanks may repeat."""
        raw = (self.cleaned_data.get("uis_employee_id") or "").strip()
        if raw and not raw.isdigit():
            raise ValidationError(_("ID сотрудника UIS — только цифры."), code="uis_employee_digits")
        if not raw:
            return ""
        clash = StaffVpbxProfile.objects.filter(uis_employee_id=raw)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(
                _("Этот ID сотрудника UIS уже записан у другого сотрудника."),
                code="uis_employee_taken",
            )
        return raw

    def clean_uis_webrtc_token(self) -> str:
        """Keep the stored token when the field is submitted empty."""
        value = (self.cleaned_data.get("uis_webrtc_token") or "").strip()
        if not value and self.instance.pk:
            return self.instance.uis_webrtc_token
        return value

    def clean(self) -> dict[str, Any]:
        """Apply the «delete token» checkbox; refuse a contradictory submit."""
        cleaned = super().clean() or {}
        if cleaned.get("clear_uis_webrtc_token"):
            typed = (self.data.get(self.add_prefix("uis_webrtc_token")) or "").strip()
            if typed:
                raise ValidationError(
                    _("Нельзя одновременно ввести новый токен и удалить токен."),
                    code="token_conflict",
                )
            cleaned["uis_webrtc_token"] = ""
        return cleaned
