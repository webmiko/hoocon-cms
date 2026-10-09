"""URL routes for CRM integrations (Mango telephony webhook)."""

from __future__ import annotations

from django.urls import path, re_path

from crm.telephony_views import MangoEventsView, NovosystemEventsView

urlpatterns = [
    path("mango/events/", MangoEventsView.as_view(), name="mango-events"),
    # Mango appends the event to the base URL: …/mango/events/call, …/summary,
    # …/recording, …/record/added — no trailing slash. Type is read from the body.
    re_path(r"^mango/events/(?P<kind>[a-z_]+(?:/[a-z_]+)?)/?$", MangoEventsView.as_view(), name="mango-events-kind"),
    path("novosystem/events/", NovosystemEventsView.as_view(), name="novosystem-events"),
]
