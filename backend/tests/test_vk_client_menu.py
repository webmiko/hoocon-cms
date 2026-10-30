"""VK inline keyboard must fit platform limits (rows, open_link per row)."""

from __future__ import annotations

import json

from social.vk_client_menu import main_menu_keyboard_vk


def test_main_menu_keyboard_vk_row_limits() -> None:
    """VK rejects >5 rows and >2 open_link buttons in one row."""
    data = json.loads(main_menu_keyboard_vk())
    rows = data["buttons"]
    assert len(rows) <= 5
    for row in rows:
        open_links = [b for b in row if b.get("action", {}).get("type") == "open_link"]
        assert len(open_links) <= 2
