"""URL routes for sitesettings public API."""

from __future__ import annotations

from django.urls import path

from sitesettings.views import PublicSettingsView

urlpatterns = [
    path("public/", PublicSettingsView.as_view(), name="settings-public"),
]
