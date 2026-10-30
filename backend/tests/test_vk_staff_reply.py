"""Staff VK reply helpers (keyboard, alert mid cache)."""

from __future__ import annotations

import json

import pytest
from django.core.cache import cache

from social.vk_staff_reply import (
    load_support_alert_mid,
    staff_support_alert_keyboard,
    store_support_alert_mid,
)


@pytest.mark.django_db
def test_staff_support_alert_keyboard_has_reply_button() -> None:
    raw = staff_support_alert_keyboard(12)
    data = json.loads(raw)
    labels = [(btn.get("action") or {}).get("label") or "" for row in data["buttons"] for btn in row]
    assert "Ответить" in labels
    assert "📝 Заметка" in labels


def test_store_and_load_support_alert_mid() -> None:
    cache.clear()
    store_support_alert_mid(5, "9001", "42", "alert text")
    loaded = load_support_alert_mid(5, "9001")
    assert loaded == {"cmid": "42", "text": "alert text"}
    cache.clear()
