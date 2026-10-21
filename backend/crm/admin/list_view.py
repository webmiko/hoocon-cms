"""Desktop choice between changelist cards and a table. Phones stay cards."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, QueryDict

_VIEWS = frozenset({"cards", "rows"})
_SESSION_KEY = "hoocon_list_view"


def remember_list_view(request: HttpRequest) -> dict[str, str]:
    """Store ``?view=cards|rows`` and drop it before Django builds the changelist.

    An unknown value is ignored. The next visit without the parameter keeps
    the last choice. The default is cards, which is how the lists open now.

    Args:
        request: Admin changelist request. ``GET`` is replaced without ``view``.

    Returns:
        Template keys for the toggle and the active mode.
    """
    original = request.GET.copy()
    raw = (original.get("view") or "").strip().lower()
    if raw in _VIEWS:
        view = raw
        request.session[_SESSION_KEY] = view
    else:
        stored = request.session.get(_SESSION_KEY)
        view = stored if isinstance(stored, str) and stored in _VIEWS else "cards"
    params = original.copy()
    params.pop("view", None)
    request.GET = params  # type: ignore[assignment]
    return {
        "hoocon_list_view": view,
        "hoocon_list_view_cards_url": _with_view(params, "cards"),
        "hoocon_list_view_rows_url": _with_view(params, "rows"),
    }


def _with_view(params: QueryDict, view: str) -> str:
    copied: Any = params.copy()
    copied["view"] = view
    return f"?{copied.urlencode()}"
