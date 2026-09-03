"""URL routes for public analytics API."""

from __future__ import annotations

from django.urls import path

from analytics.views import PageHitView

urlpatterns = [
    path("hit/", PageHitView.as_view(), name="analytics-hit"),
]
