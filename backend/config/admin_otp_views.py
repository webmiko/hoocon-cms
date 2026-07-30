"""Views and AdminSite install for passwordless Admin Email OTP."""

from __future__ import annotations

import logging
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import REDIRECT_FIELD_NAME
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

from config.admin_otp import (
    AdminOtpDeliveryError,
    AdminOtpVerifyError,
    admin_email_otp_enabled,
    clear_admin_otp_challenge,
    find_staff_user_for_otp,
    get_pending_admin_otp_user,
    mask_email,
    resend_admin_otp,
    start_admin_otp_challenge,
    verify_admin_otp,
)

logger = logging.getLogger(__name__)

_OTP_TEMPLATE = "admin/otp.html"
_OTP_LOGIN_TEMPLATE = "admin/otp_login.html"
_GENERIC_OTP_FAIL = "Не удалось отправить код. Проверьте логин или email."


def _otp_username_widget() -> forms.Widget:
    """Unfold-styled username field when package is available."""
    try:
        from unfold.widgets import UnfoldAdminTextInputWidget
    except ImportError:
        return forms.TextInput(
            attrs={
                "autocapitalize": "none",
                "autocomplete": "username",
                "autofocus": True,
            },
        )
    return UnfoldAdminTextInputWidget(
        attrs={
            "autocapitalize": "none",
            "autocomplete": "username",
            "autofocus": True,
        },
    )


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


def _record_axes_failure(request: HttpRequest, username: str) -> None:
    """Feed django-axes from custom OTP login failures."""
    user_login_failed.send(
        sender=__name__,
        credentials={"username": username},
        request=request,
    )


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

    def form_valid(self, form: Any) -> HttpResponse:
        login = str(form.cleaned_data.get("username") or "").strip()
        user = find_staff_user_for_otp(login)
        if user is None or not (getattr(user, "email", "") or "").strip():
            _record_axes_failure(self.request, login)
            form.add_error(None, _GENERIC_OTP_FAIL)
            return self.form_invalid(form)

        next_url = self.get_success_url()
        try:
            start_admin_otp_challenge(self.request, user, next_url=next_url)
        except AdminOtpDeliveryError as exc:
            _record_axes_failure(self.request, login)
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        return HttpResponseRedirect(reverse("admin:otp"))


@never_cache
@csrf_protect
@login_not_required
@require_http_methods(["GET", "POST"])
def admin_otp_verify_view(request: HttpRequest) -> HttpResponse:
    """Enter the emailed 6-digit code."""
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
            # Backend that authenticated the session (Axes-compatible).
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

    context = {
        **site.each_context(request),
        "title": "Код подтверждения",
        "subtitle": None,
        "masked_email": mask_email(getattr(user, "email", "") or ""),
        "error": error,
        "otp_resend_url": reverse("admin:otp_resend"),
        "otp_cancel_url": reverse("admin:otp_cancel"),
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
    """AdminSite.login with OTP or classic password form."""
    from django.contrib.admin.forms import AdminAuthenticationForm

    if request.method == "GET" and self.has_permission(request):
        index_path = reverse("admin:index", current_app=self.name)
        return HttpResponseRedirect(index_path)

    if request.method == "GET" and admin_email_otp_enabled() and get_pending_admin_otp_user(request):
        return HttpResponseRedirect(reverse("admin:otp"))

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

    request.current_app = self.name

    if admin_email_otp_enabled():
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
