"""Integrations card and menu gate for the manager-request widget."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from staffrequests.services import can_file, can_toggle, requests_enabled


def menu_visible(request: HttpRequest) -> bool:
    """Sidebar and phone nav show the queue only while the widget is on."""
    user = getattr(request, "user", None)
    return requests_enabled() and can_file(user)


def integration_card(request: HttpRequest) -> dict[str, Any]:
    """One card for the integrations page. Present even when the widget is off."""
    enabled = requests_enabled()
    user = getattr(request, "user", None)
    may_toggle = can_toggle(user)
    return {
        "template_name": "admin/staffrequests/widget_card.html",
        "name": "Техподдержка",
        "enabled": enabled,
        "status": "on" if enabled else "off",
        "status_label": "Включён" if enabled else "Выключен",
        "hint": (
            "Менеджеры пишут баг, доработку, вопрос или просьбу. "
            "Очередь видят администратор и суперпользователь. Выключено — пункта меню нет."
        ),
        "save_url": reverse("admin:staffrequests_staffrequest_toggle"),
        "form_id": "staffreq-toggle" if may_toggle else "",
        "open_url": reverse("admin:staffrequests_staffrequest_changelist") if enabled else "",
        "can_toggle": may_toggle,
    }
