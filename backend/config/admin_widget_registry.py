"""Admin widgets the integrations page lists. Each widget owns its card."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def admin_widget_cards(request: HttpRequest) -> list[dict[str, Any]]:
    """Cards besides telephony. Removing a widget means deleting its line here."""
    from staffrequests.widget import integration_card

    return [integration_card(request)]
