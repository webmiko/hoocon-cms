"""URL routes for ``/api/staff/``."""

from __future__ import annotations

from django.urls import path

from staff_api.views import (
    BadgesView,
    ClientActivityCreateView,
    ClientDetailView,
    ClientEmailCreateView,
    ClientListView,
    ConversationAssignView,
    ConversationCloseView,
    ConversationDetailView,
    ConversationListView,
    ConversationMessagesView,
    ConversationReadView,
    DeviceDeleteView,
    DeviceRegisterView,
    LeadDetailView,
    LeadListView,
    LeadStatusView,
    LeadTakeView,
    LogoutView,
    MeView,
    OtpResendView,
    OtpStartView,
    OtpVerifyView,
)

urlpatterns = [
    path("auth/otp/start/", OtpStartView.as_view(), name="staff-otp-start"),
    path("auth/otp/verify/", OtpVerifyView.as_view(), name="staff-otp-verify"),
    path("auth/otp/resend/", OtpResendView.as_view(), name="staff-otp-resend"),
    path("auth/logout/", LogoutView.as_view(), name="staff-logout"),
    path("me/", MeView.as_view(), name="staff-me"),
    path("badges/", BadgesView.as_view(), name="staff-badges"),
    path("leads/", LeadListView.as_view(), name="staff-leads"),
    path("leads/<int:pk>/", LeadDetailView.as_view(), name="staff-lead-detail"),
    path("leads/<int:pk>/take/", LeadTakeView.as_view(), name="staff-lead-take"),
    path("leads/<int:pk>/status/", LeadStatusView.as_view(), name="staff-lead-status"),
    path("clients/", ClientListView.as_view(), name="staff-clients"),
    path("clients/<int:pk>/", ClientDetailView.as_view(), name="staff-client-detail"),
    path(
        "clients/<int:pk>/activities/",
        ClientActivityCreateView.as_view(),
        name="staff-client-activities",
    ),
    path(
        "clients/<int:pk>/emails/",
        ClientEmailCreateView.as_view(),
        name="staff-client-emails",
    ),
    path("conversations/", ConversationListView.as_view(), name="staff-conversations"),
    path(
        "conversations/<int:pk>/",
        ConversationDetailView.as_view(),
        name="staff-conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        ConversationMessagesView.as_view(),
        name="staff-conversation-messages",
    ),
    path(
        "conversations/<int:pk>/assign/",
        ConversationAssignView.as_view(),
        name="staff-conversation-assign",
    ),
    path(
        "conversations/<int:pk>/close/",
        ConversationCloseView.as_view(),
        name="staff-conversation-close",
    ),
    path(
        "conversations/<int:pk>/read/",
        ConversationReadView.as_view(),
        name="staff-conversation-read",
    ),
    path("devices/", DeviceRegisterView.as_view(), name="staff-devices"),
    path("devices/<int:pk>/", DeviceDeleteView.as_view(), name="staff-device-delete"),
]
