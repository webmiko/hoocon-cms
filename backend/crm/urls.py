"""URL routes for CRM integrations (Mango telephony webhook)."""

from __future__ import annotations

from django.urls import path

from crm.telephony_views import MangoEventsView

urlpatterns = [
    path("mango/events/", MangoEventsView.as_view(), name="mango-events"),
]
