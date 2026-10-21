"""Planned-call status is visible in the list, sortable, and editable on the card."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from crm.models import Company, PlannedTouch, PlannedTouchStatus


def _touch(name: str, *, status: str, key: str) -> PlannedTouch:
    org = Company.objects.create(name=name)
    return PlannedTouch.objects.create(
        company=org,
        starts_at=timezone.now(),
        title=f"Звонок: {name}",
        status=status,
        dedupe_key=key,
    )


@pytest.mark.django_db
def test_planned_call_list_shows_status_and_sorts_by_it(client: Any) -> None:
    """The changelist chip is the progress, and the status column orders the rows."""
    user = get_user_model().objects.create_superuser("status-admin", "status-admin@example.com", "password12")
    planned = _touch("Ротадо", status=PlannedTouchStatus.PLANNED, key="status-planned")
    reached = _touch("Интелвент", status=PlannedTouchStatus.REACHED, key="status-reached")
    client.force_login(user)

    page = client.get(reverse("admin:crm_plannedtouch_changelist"))
    html = page.content.decode()
    assert page.status_code == 200
    assert "hoocon-lead-status--draft" in html
    assert "Запланирован" in html
    assert "hoocon-lead-status--accepted" in html
    assert "Дозвонились" in html
    css = open("static/admin/css/hoocon-unfold-extras.css", encoding="utf-8").read()
    dark_draft = css.split(".dark .hoocon-lead-status--draft {", 1)[1].split("}", 1)[0]
    assert "background:" in dark_draft
    assert "#f5f5f4" in dark_draft
    assert "border-color:" in dark_draft

    # list_display: starts_at, title, status_badge → column 3 sorts by status.
    ordered = client.get(reverse("admin:crm_plannedtouch_changelist") + "?o=3")
    body = ordered.content.decode()
    assert body.index(planned.title) < body.index(reached.title)

    change = client.get(reverse("admin:crm_plannedtouch_change", args=[planned.pk]))
    form = change.content.decode()
    assert 'name="status"' in form
    assert 'value="no_answer"' in form
    saved = client.post(
        reverse("admin:crm_plannedtouch_change", args=[planned.pk]),
        {
            "status": PlannedTouchStatus.NO_ANSWER,
            "title": planned.title,
            "kind": "call",
            "starts_at_0": timezone.localtime(planned.starts_at).date().isoformat(),
            "starts_at_1": timezone.localtime(planned.starts_at).strftime("%H:%M:%S"),
            "company": planned.company_id,
            "remind_before_minutes": 60,
            "note": "",
            "_save": "Сохранить",
        },
    )
    assert saved.status_code == 302
    planned.refresh_from_db()
    assert planned.status == PlannedTouchStatus.NO_ANSWER
