"""One-click slices above a list: «Новые 4», «Мои в работе 2».

The side filters of the admin list are named after database columns and
hide in a panel. A manager does not know which one to press. Tabs answer
the four questions that decide the day and show how many rows each holds.

A tab only sets ordinary list filters in the address, so the list, the
pagination and the search keep working as before and nothing is hidden
from the manager's scope: counts come from the already scoped queryset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from django.db.models import Count, Q, QuerySet


@dataclass(frozen=True)
class TabSpec:
    """A tab: the filters it sets and the rows it counts."""

    label: str
    params: dict[str, str] = field(default_factory=dict)
    # None means «everything»: no filter, count the whole list.
    rows: Q | None = None
    hint: str = ""


@dataclass(frozen=True)
class Tab:
    """A rendered tab."""

    label: str
    url: str
    count: int
    active: bool
    hint: str = ""


def build_list_tabs(params: Any, queryset: QuerySet[Any], specs: list[TabSpec]) -> list[Tab]:
    """Tabs for the current address.

    Args:
        params: the request's ``GET`` (a QueryDict) without view/sort keys.
        queryset: the list's scoped queryset.
        specs: tabs in display order; a spec without params is the reset tab.
    """
    controlled = {key for spec in specs for key in spec.params}
    current = {key: params.get(key, "") for key in controlled if params.get(key) is not None}
    keep = [(key, value) for key in params for value in params.getlist(key) if key not in controlled and key != "p"]

    aggregates = {f"tab_{index}": Count("pk", filter=spec.rows, distinct=True) for index, spec in enumerate(specs)}
    counts = queryset.order_by().aggregate(**aggregates)

    tabs: list[Tab] = []
    for index, spec in enumerate(specs):
        query = urlencode([*keep, *spec.params.items()])
        tabs.append(
            Tab(
                label=spec.label,
                url=f"?{query}" if query else "?",
                count=int(counts[f"tab_{index}"] or 0),
                active=current == spec.params,
                hint=spec.hint,
            ),
        )
    return tabs
