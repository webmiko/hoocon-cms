"""VK Bot keyboard JSON for messages.send."""

from __future__ import annotations

import json
from typing import Any


def vk_inline_keyboard(rows: list[list[dict[str, str]]]) -> str:
    """Build ``keyboard`` JSON for ``messages.send``.

    Each cell: ``{"type": "callback"|"link", "text": "...", "payload"|"url": "..."}``.
    """
    buttons: list[list[dict[str, Any]]] = []
    for row in rows:
        btn_row: list[dict[str, Any]] = []
        for cell in row:
            text = (cell.get("text") or "").strip()
            if not text:
                continue
            if cell.get("type") == "link":
                url = (cell.get("url") or "").strip()
                if url:
                    btn_row.append(
                        {
                            "action": {
                                "type": "open_link",
                                "link": url,
                                "label": text,
                            },
                        },
                    )
            else:
                payload = (cell.get("payload") or text)[:255]
                btn_row.append(
                    {
                        "action": {
                            "type": "callback",
                            "label": text,
                            "payload": payload,
                        },
                    },
                )
        if btn_row:
            buttons.append(btn_row)
    return json.dumps({"inline": True, "buttons": buttons}, ensure_ascii=False)
