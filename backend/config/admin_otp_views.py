"""Views and AdminSite install for passwordless Admin Email OTP.

When OTP is enabled, staff enter username/email → emailed 6-digit code.
Superusers additionally get break-glass: permanent password (``?mode=password``)
and single-use recovery codes (``?mode=recovery`` / OTP verify field).
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import REDIRECT_FIELD_NAME, authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.signals import user_login_failed
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse, HttpResponseBase, HttpResponseRedirect
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from accounts.recovery_codes import consume_recovery_code
from config.admin_otp import (
    AdminOtpDeliveryError,
    AdminOtpVerifyError,
    admin_email_otp_enabled,
    begin_admin_otp_session,
    clear_admin_otp_challenge,
    consume_otp_request_quota,
    find_staff_user_for_otp,
    get_pending_admin_otp_user,
    mask_email,
    pending_otp_email_failed,
    resend_admin_otp,
    start_admin_otp_challenge,
    verify_admin_otp,
)

logger = logging.getLogger(__name__)

_OTP_TEMPLATE = "admin/otp.html"
_OTP_LOGIN_TEMPLATE = "admin/otp_login.html"
_OTP_PASSWORD_TEMPLATE = "admin/otp_password_login.html"
_OTP_RECOVERY_TEMPLATE = "admin/otp_recovery_login.html"
_GENERIC_OTP_FAIL = "Не удалось отправить код. Проверьте логин или email."
_GENERIC_BREAK_GLASS_FAIL = "Неверный логин или пароль."
_GENERIC_RECOVERY_FAIL = "Неверный логин или резервный код."


def _otp_username_widget(*, autofocus: bool = True) -> forms.Widget:
    """Unfold-styled username field when package is available."""
    attrs: dict[str, Any] = {
        "autocapitalize": "none",
        "autocomplete": "username",
    }
    if autofocus:
        attrs["autofocus"] = True
    try:
        from unfold.widgets import UnfoldAdminTextInputWidget
    except ImportError:
        return forms.TextInput(attrs=attrs)
    return UnfoldAdminTextInputWidget(attrs=attrs)


def _otp_password_widget() -> forms.Widget:
    """Unfold-styled password field when package is available."""
    attrs = {"autocomplete": "current-password"}
    try:
        from unfold.widgets import UnfoldAdminPasswordWidget
    except ImportError:
        return forms.PasswordInput(attrs=attrs)
    return UnfoldAdminPasswordWidget(attrs=attrs)


def _otp_recovery_widget() -> forms.Widget:
    """Recovery-code text input (not a password manager field)."""
    attrs = {
        "autocapitalize": "characters",
        "autocomplete": "one-time-code",
        "spellcheck": "false",
        "placeholder": "XXXX-XXXX",
    }
    try:
        from unfold.widgets import UnfoldAdminTextInputWidget
    except ImportError:
        return forms.TextInput(attrs=attrs)
    return UnfoldAdminTextInputWidget(attrs=attrs)


class AdminOtpRequestForm(forms.Form):
    """Username or email only — no password (OTP path)."""

    username = forms.CharField(
        label="Логин или email",
        max_length=254,
        widget=_otp_username_widget(),
    )

    def __init__(self, request: HttpRequest | None = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        super().__init__(*args, **kwargs)


class AdminSuperuserPasswordForm(forms.Form):
    """Break-glass password login for superusers while OTP is enabled."""

    username = forms.CharField(
        label="Логин или email",
        max_length=254,
        widget=_otp_username_widget(),
    )
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=_otp_password_widget(),
    )

    def __init__(self, request: HttpRequest | None = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.user_cache: Any = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        username = str(cleaned.get("username") or "").strip()
        password = cleaned.get("password") or ""
        if not username or not password:
            return cleaned

        user = authenticate(
            self.request,
            username=username,
            password=password,
        )
        # Also try email-as-username lookup when authenticate failed on raw login.
        if user is None and "@" in username:
            from django.contrib.auth import get_user_model

            user_model = get_user_model()
            match = user_model.objects.filter(
                email__iexact=username,
                is_active=True,
                is_staff=True,
            ).first()
            if match is not None:
                user = authenticate(
                    self.request,
                    username=match.get_username(),
                    password=password,
                )

        if (
            user is None
            or not getattr(user, "is_active", False)
            or not getattr(user, "is_staff", False)
            or not getattr(user, "is_superuser", False)
            or not user.has_usable_password()
        ):
            raise forms.ValidationError(_GENERIC_BREAK_GLASS_FAIL, code="invalid_login")

        self.user_cache = user
        return cleaned


class AdminSuperuserRecoveryForm(forms.Form):
    """Break-glass recovery-code login for superusers (no email required)."""

    username = forms.CharField(
        label="Логин или email",
        max_length=254,
        widget=_otp_username_widget(),
    )
    recovery_code = forms.CharField(
        label="Резервный код",
        max_length=32,
        widget=_otp_recovery_widget(),
    )

    def __init__(self, request: HttpRequest | None = None, *args: Any, **kwargs: Any) -> None:
        self.request = request
        self.user_cache: Any = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        username = str(cleaned.get("username") or "").strip()
        code = str(cleaned.get("recovery_code") or "").strip()
        if not username or not code:
            return cleaned

        # Resolve without allowlist gate (break-glass when SMTP/allowlist blocks OTP).
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        qs = user_model.objects.filter(is_active=True, is_staff=True)
        user = qs.filter(username__iexact=username).first()
        if user is None and "@" in username:
            user = qs.filter(email__iexact=username).first()

        if user is None or not getattr(user, "is_superuser", False) or not consume_recovery_code(user, code):
            raise forms.ValidationError(_GENERIC_RECOVERY_FAIL, code="invalid_recovery")

        self.user_cache = user
        return cleaned


def _record_axes_failure(request: HttpRequest, username: str) -> None:
    """Feed django-axes from custom OTP login failures."""
    user_login_failed.send(
        sender=__name__,
        credentials={"username": username},
        request=request,
    )


def _login_mode(request: HttpRequest) -> str:
    """Return ``password``, ``recovery``, or ``otp`` (default)."""
    raw = str(request.GET.get("mode") or request.POST.get("mode") or "").strip().lower()
    if raw in {"password", "recovery"}:
        return raw
    return "otp"


def _mode_login_url(mode: str) -> str:
    base = reverse("admin:login")
    if mode in {"password", "recovery"}:
        return f"{base}?{urlencode({'mode': mode})}"
    return base


@method_decorator(never_cache, name="dispatch")
class AdminPasswordlessOtpLoginView(LoginView):
    """Request OTP by username/email; do not authenticate until code verify."""

    redirect_authenticated_user = False
    form_class = AdminOtpRequestForm  # type: ignore[assignment]
    template_name = _OTP_LOGIN_TEMPLATE

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["password_login_url"] = _mode_login_url("password")
        context["recovery_login_url"] = _mode_login_url("recovery")
        return context

    def get_success_url(self) -> str:
        """Stay inside Admin after OTP (never Django's /accounts/profile/)."""
        url = super().get_success_url()
        if isinstance(url, str) and url.startswith("/admin"):
            return url
        return reverse("admin:index")

    def form_valid(self, form: Any) -> HttpResponse:
        login = str(form.cleaned_data.get("username") or "").strip()
        try:
            consume_otp_request_quota(self.request)
        except AdminOtpDeliveryError as exc:
            _record_axes_failure(self.request, login)
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        user = find_staff_user_for_otp(login)
        if user is None or not (getattr(user, "email", "") or "").strip():
            _record_axes_failure(self.request, login)
            form.add_error(None, _GENERIC_OTP_FAIL)
            return self.form_invalid(form)

        next_url = self.get_success_url()
        try:
            start_admin_otp_challenge(self.request, user, next_url=next_url)
        except AdminOtpDeliveryError as exc:
            # Superuser break-glass: open verify session without emailed code.
            if getattr(user, "is_superuser", False):
                clear_admin_otp_challenge(self.request)
                begin_admin_otp_session(
                    self.request,
                    user,
                    next_url=next_url,
                    email_failed=True,
                )
                messages.warning(
                    self.request,
                    "Не удалось отправить код на email. Введите резервный код супер-админа или войдите паролем.",
                )
                return HttpResponseRedirect(reverse("admin:otp"))
            _record_axes_failure(self.request, login)
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        return HttpResponseRedirect(reverse("admin:otp"))


@method_decorator(never_cache, name="dispatch")
class AdminSuperuserPasswordLoginView(LoginView):
    """Permanent-password break-glass for superusers while OTP is on."""

    redirect_authenticated_user = False
    form_class = AdminSuperuserPasswordForm  # type: ignore[assignment]
    template_name = _OTP_PASSWORD_TEMPLATE

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["otp_login_url"] = reverse("admin:login")
        context["recovery_login_url"] = _mode_login_url("recovery")
        return context

    def get_success_url(self) -> str:
        url = super().get_success_url()
        if isinstance(url, str) and url.startswith("/admin"):
            return url
        return reverse("admin:index")

    def form_valid(self, form: Any) -> HttpResponse:
        user = form.user_cache
        clear_admin_otp_challenge(self.request)
        auth_login(
            self.request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form: Any) -> HttpResponse:
        login = str(form.data.get("username") or "").strip()
        if login:
            _record_axes_failure(self.request, login)
        return super().form_invalid(form)


@method_decorator(never_cache, name="dispatch")
class AdminSuperuserRecoveryLoginView(LoginView):
    """Recovery-code break-glass for superusers (no SMTP required)."""

    redirect_authenticated_user = False
    form_class = AdminSuperuserRecoveryForm  # type: ignore[assignment]
    template_name = _OTP_RECOVERY_TEMPLATE

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["otp_login_url"] = reverse("admin:login")
        context["password_login_url"] = _mode_login_url("password")
        return context

    def get_success_url(self) -> str:
        url = super().get_success_url()
        if isinstance(url, str) and url.startswith("/admin"):
            return url
        return reverse("admin:index")

    def form_valid(self, form: Any) -> HttpResponse:
        user = form.user_cache
        clear_admin_otp_challenge(self.request)
        auth_login(
            self.request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form: Any) -> HttpResponse:
        login = str(form.data.get("username") or "").strip()
        if login:
            _record_axes_failure(self.request, login)
        return super().form_invalid(form)


@never_cache
@csrf_protect
@login_not_required
@require_http_methods(["GET", "POST"])
def admin_otp_verify_view(request: HttpRequest) -> HttpResponse:
    """Enter the emailed 6-digit code (or superuser recovery code)."""
    site = admin.site
    user = get_pending_admin_otp_user(request)
    if user is None:
        messages.error(request, "Сессия подтверждения истекла. Войдите снова.")
        return HttpResponseRedirect(reverse("admin:login"))

    error: str | None = None
    if request.method == "POST":
        raw_code = str(request.POST.get("otp_code", ""))
        try:
            verified_user, next_url = verify_admin_otp(request, raw_code)
            auth_login(
                request,
                verified_user,  # type: ignore[arg-type]
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return HttpResponseRedirect(next_url)
        except AdminOtpVerifyError as exc:
            error = str(exc)
            _record_axes_failure(request, getattr(user, "get_username", lambda: "")())
            if get_pending_admin_otp_user(request) is None:
                messages.error(request, error)
                return HttpResponseRedirect(reverse("admin:login"))

    email_failed = pending_otp_email_failed(request)
    context = {
        **site.each_context(request),
        "title": "Код подтверждения",
        "subtitle": None,
        "masked_email": mask_email(getattr(user, "email", "") or ""),
        "error": error,
        "email_failed": email_failed,
        "allow_recovery_hint": bool(getattr(user, "is_superuser", False)),
        "otp_resend_url": reverse("admin:otp_resend"),
        "otp_cancel_url": reverse("admin:otp_cancel"),
        "password_login_url": _mode_login_url("password"),
        "recovery_login_url": _mode_login_url("recovery"),
        "site_title": site.site_title,
        "site_header": site.site_header,
        "has_permission": False,
    }
    return render(request, _OTP_TEMPLATE, context)


@never_cache
@csrf_protect
@login_not_required
@require_http_methods(["POST"])
def admin_otp_resend_view(request: HttpRequest) -> HttpResponse:
    """Resend a fresh OTP code."""
    try:
        consume_otp_request_quota(request)
        resend_admin_otp(request)
        messages.success(request, "Новый код отправлен на email.")
    except AdminOtpDeliveryError as exc:
        messages.error(request, str(exc))
    except AdminOtpVerifyError as exc:
        if get_pending_admin_otp_user(request) is None:
            messages.error(request, str(exc))
            return HttpResponseRedirect(reverse("admin:login"))
        messages.error(request, str(exc))
    return HttpResponseRedirect(reverse("admin:otp"))


@never_cache
@login_not_required
@require_http_methods(["GET", "POST"])
def admin_otp_cancel_view(request: HttpRequest) -> HttpResponse:
    """Cancel OTP challenge and return to login."""
    clear_admin_otp_challenge(request)
    return HttpResponseRedirect(reverse("admin:login"))


@method_decorator(never_cache)
@login_not_required
def _patched_login(
    self: Any,
    request: HttpRequest,
    extra_context: dict[str, Any] | None = None,
) -> HttpResponseBase:
    """AdminSite.login with OTP, superuser break-glass, or classic password."""
    from django.contrib.admin.forms import AdminAuthenticationForm

    if request.method == "GET" and self.has_permission(request):
        index_path = reverse("admin:index", current_app=self.name)
        return HttpResponseRedirect(index_path)

    mode = _login_mode(request)
    # Pending OTP challenge: stay on verify unless user explicitly opens break-glass.
    if request.method == "GET" and admin_email_otp_enabled() and mode == "otp" and get_pending_admin_otp_user(request):
        return HttpResponseRedirect(reverse("admin:otp"))

    from accounts.passkey_views import passkey_login_context

    context = {
        **self.each_context(request),
        "title": "Вход",
        "subtitle": None,
        "app_path": request.get_full_path(),
        "username": request.user.get_username(),
    }
    if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
        context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=self.name)
    context.update(extra_context or {})
    context.update(passkey_login_context(request))

    request.current_app = self.name

    if admin_email_otp_enabled():
        if mode == "password":
            return AdminSuperuserPasswordLoginView.as_view(
                extra_context=context,
                template_name=_OTP_PASSWORD_TEMPLATE,
            )(request)
        if mode == "recovery":
            return AdminSuperuserRecoveryLoginView.as_view(
                extra_context=context,
                template_name=_OTP_RECOVERY_TEMPLATE,
            )(request)
        return AdminPasswordlessOtpLoginView.as_view(
            extra_context=context,
            template_name=self.login_template or _OTP_LOGIN_TEMPLATE,
        )(request)

    defaults = {
        "extra_context": context,
        "authentication_form": self.login_form or AdminAuthenticationForm,
        "template_name": self.login_template or "admin/login.html",
    }
    return LoginView.as_view(**defaults)(request)


def install_admin_email_otp() -> None:
    """Patch default admin.site: login + otp/resend/cancel URLs."""
    site = admin.site
    if getattr(site, "_hoocon_admin_otp_installed", False):
        return

    original_get_urls = site.get_urls

    def get_urls() -> list[Any]:
        return [
            path("otp/", admin_otp_verify_view, name="otp"),
            path("otp/resend/", admin_otp_resend_view, name="otp_resend"),
            path("otp/cancel/", admin_otp_cancel_view, name="otp_cancel"),
        ] + original_get_urls()

    site.get_urls = get_urls  # type: ignore[method-assign]
    site.login = _patched_login.__get__(site, type(site))  # type: ignore[method-assign]
    site._hoocon_admin_otp_installed = True  # type: ignore[attr-defined]
    logger.debug("Admin email OTP installed on default AdminSite")
