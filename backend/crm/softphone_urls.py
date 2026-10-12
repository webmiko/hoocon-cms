"""Routes for the browser softphone; mounted before ``admin.site.urls``."""

from __future__ import annotations

from django.urls import path

from crm import softphone

urlpatterns = [
    path("", softphone.window_view, name="crm_softphone_window"),
    path("session/", softphone.session_view, name="crm_softphone_session"),
    path("lookup/", softphone.lookup_view, name="crm_softphone_lookup"),
]
