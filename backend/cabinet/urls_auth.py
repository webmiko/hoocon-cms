"""URL routes for ``/api/auth/*`` (client cabinet auth)."""

from __future__ import annotations

from django.urls import path

from cabinet import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="client-register"),
    path("login/", views.LoginView.as_view(), name="client-login"),
    path("otp/start/", views.OtpStartView.as_view(), name="client-otp-start"),
    path("otp/verify/", views.OtpVerifyView.as_view(), name="client-otp-verify"),
    path("otp/resend/", views.OtpResendView.as_view(), name="client-otp-resend"),
    path("logout/", views.LogoutView.as_view(), name="client-logout"),
    path("me/", views.AuthMeView.as_view(), name="client-auth-me"),
]
