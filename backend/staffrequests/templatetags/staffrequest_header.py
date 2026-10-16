"""Breadcrumb for the one-model tech-support app."""

from __future__ import annotations

from typing import Any

from django import template
from django.urls import reverse

register = template.Library()


def _path(link: object) -> str:
    return str(link or "").rstrip("/")


@register.filter
def single_staffrequest_crumb(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the app-index crumb. The queue link is the way back."""
    app_index = _path(reverse("admin:app_list", args=["staffrequests"]))
    listing = _path(reverse("admin:staffrequests_staffrequest_changelist"))
    kept: list[dict[str, Any]] = []
    for part in parts:
        link = _path(part.get("link"))
        if link == app_index:
            continue
        if link == listing:
            part = {**part, "title": "Техподдержка"}
        kept.append(part)
    return kept
