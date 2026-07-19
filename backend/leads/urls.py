"""URL routes for the public Lead API.

Spec: ПЛАН §6 Iter 3 — POST /api/leads/; docs/readiness-backend-ux.md §2.3.

Included under `api/leads/` in config/urls.py, so this module maps the
root (`""`) to the create action.
"""

from __future__ import annotations

from django.urls import path

from leads.views import LeadViewSet

urlpatterns = [
    # POST /api/leads/ — public lead creation (honeypot + throttle + Celery email).
    # Explicit action map (no router) — the viewset is create-only (no list/retrieve).
    path(
        "",
        LeadViewSet.as_view({"post": "create"}),
        name="lead-list",
    ),
]
