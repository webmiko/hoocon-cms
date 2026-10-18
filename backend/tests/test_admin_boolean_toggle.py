"""Admin booleans use the integrations toggle; row picks stay checkboxes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

_EXTRAS = Path(__file__).resolve().parents[1] / "static/admin/css/hoocon-unfold-extras.css"


def test_boolean_toggle_css_swaps_caption_with_state() -> None:
    """Off caption is visible until the switch is checked, then the on caption."""
    css = _EXTRAS.read_text(encoding="utf-8")  # source-lint: Unfold loads this file; :has is the caption switch
    assert ".hoocon-bool-toggle__state--off" in css
    assert ".hoocon-bool-toggle:has(input:checked) .hoocon-bool-toggle__state--off" in css
    assert ".hoocon-bool-toggle:has(input:checked) .hoocon-bool-toggle__state--on" in css
    assert '.inline-group[data-inline-type="stacked"] .aligned label.hoocon-bool-toggle' in css


@pytest.mark.django_db
def test_staff_profile_booleans_are_toggles_with_captions() -> None:
    """Profile flags and the account switches show Выключено/Включено, not a bare checkbox."""
    user = User.objects.create_superuser(username="toggle-admin", email="toggle@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)
    html = client.get(reverse("admin:auth_user_change", args=[user.pk])).content.decode()

    assert html.count('class="hoocon-toggle"') >= 5
    main_form = re.search(
        r'<label class="hoocon-bool-toggle"><input[^>]*id="id_is_superuser"',
        html,
    )
    assert main_form is not None
    assert "Выключено" in html
    assert "Включено" in html
    assert "STARTTLS" in html
    assert ">SSL<" in html
    clear = re.search(r"<input\b[^>]*clear_uis_webrtc_token[^>]*>", html)
    assert clear is not None
    assert "hoocon-toggle" not in clear.group(0)


@pytest.mark.django_db
def test_changelist_row_picker_stays_a_checkbox() -> None:
    """«Выберите запись» is a multi-select, so it does not become a switch."""
    user = User.objects.create_superuser(username="toggle-list", email="list@hoocon.ru", password="x")
    client = Client()
    client.force_login(user)
    html = client.get(reverse("admin:auth_user_changelist")).content.decode()
    picker = html.split('name="_selected_action"', 1)[0][-500:]
    assert "hoocon-bool-toggle" not in picker
