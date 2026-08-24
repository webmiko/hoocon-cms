"""In-memory redirect index — one DB read per TTL instead of per request."""

from __future__ import annotations

import threading
import time
from typing import NamedTuple

TTL_SECONDS = 60


class RedirectHit(NamedTuple):
    """Active redirect target for a normalized path."""

    to_path: str
    status_code: int


_index: dict[str, RedirectHit] | None = None
_index_at: float = 0.0
_lock = threading.Lock()


def clear_redirect_index() -> None:
    """Drop cached redirect rows (tests, Admin save/delete)."""
    global _index, _index_at
    with _lock:
        _index = None
        _index_at = 0.0


def lookup_redirect(path: str) -> RedirectHit | None:
    """Return redirect target for ``path`` or ``None`` when no active rule exists."""
    global _index, _index_at
    now = time.monotonic()
    with _lock:
        if _index is None or now - _index_at >= TTL_SECONDS:
            from redirects.models import Redirect

            rows = Redirect.objects.filter(is_active=True).values_list(
                "from_path",
                "to_path",
                "status_code",
            )
            _index = {from_path: RedirectHit(to_path, status_code) for from_path, to_path, status_code in rows}
            _index_at = now
        return _index.get(path)
