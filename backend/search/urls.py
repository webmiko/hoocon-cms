"""URL routes for unified search API.

Spec: ПЛАН §6 — GET /api/search/?q=; docs/readiness-backend-ux.md §2.3.
"""

from __future__ import annotations

from django.urls import path

from search.views import SearchView

urlpatterns = [
    path("search/", SearchView.as_view(), name="api-search"),
]
