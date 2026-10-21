"""Weekly 1C stock snapshots and the decrease between two exports.

A file holds free quantity on one date, not receipts and issues. A decrease
is the earlier free quantity minus the later one. When both a receipt and a
shipment happened between two files, only the net change is visible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.http import HttpRequest
from django.urls import reverse

from catalog.etl.stock_import import (
    normalize_stock_article_key,
    sku_ids_by_stock_key,
    stock_article_is_ma_option,
)
from catalog.models import StockSnapshot, StockSnapshotLine

# (card id, rolling days, short label). Week is 7 days; months match the order cards.
SNAPSHOT_WINDOWS: tuple[tuple[str, int, str], ...] = (
    ("7", 7, "7 дн."),
    ("30", 30, "1 мес."),
    ("91", 91, "3 мес."),
    ("182", 182, "6 мес."),
    ("365", 365, "12 мес."),
)
_WINDOW_DAYS = {key: days for key, days, _label in SNAPSHOT_WINDOWS}
_REQUEST_CACHE = "_hoocon_stock_snapshots"

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
_FILENAME_DATE = re.compile(
    r"(?P<day>\d{1,2})\s+(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<year>\d{4})",
    re.IGNORECASE,
)


def stock_date_from_filename(name: str) -> date | None:
    """Read ``10 августа 2026`` or ``на 19 октября 2026`` from a file name."""
    match = _FILENAME_DATE.search(name or "")
    if match is None:
        return None
    month = _MONTHS[match.group("month").casefold()]
    try:
        return date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None


def _buckets(rows: list[tuple[str, int | None]]) -> dict[str, tuple[str, int, int]]:
    """Last numeric base and 4–20 mA quantity per article key.

    A non-numeric cell does not wipe a previous numeric row for that bucket.
    """
    base: dict[str, tuple[str, int]] = {}
    ma: dict[str, tuple[str, int]] = {}
    for code, qty in rows:
        raw = (code or "").strip()
        if not raw or qty is None:
            continue
        key = normalize_stock_article_key(raw)
        if not key:
            continue
        if stock_article_is_ma_option(raw):
            ma[key] = (raw, qty)
        else:
            base[key] = (raw, qty)
    lines: dict[str, tuple[str, int, int]] = {}
    for key in set(base) | set(ma):
        article = (base.get(key) or ma[key])[0]
        lines[key] = (article, base.get(key, ("", 0))[1], ma.get(key, ("", 0))[1])
    return lines


def record_stock_snapshot(
    rows: list[tuple[str, int | None]],
    *,
    taken_on: date,
    source_name: str = "",
) -> StockSnapshot:
    """Replace the export stored for ``taken_on`` with these rows."""
    buckets = _buckets(rows)
    with transaction.atomic():
        snapshot, _created = StockSnapshot.objects.update_or_create(
            taken_on=taken_on,
            defaults={"source_name": (source_name or "")[:300]},
        )
        snapshot.lines.all().delete()
        StockSnapshotLine.objects.bulk_create(
            [
                StockSnapshotLine(
                    snapshot=snapshot,
                    article_key=key,
                    article=article[:300],
                    qty=qty,
                    qty_ma=qty_ma,
                )
                for key, (article, qty, qty_ma) in buckets.items()
            ],
        )
    return snapshot


@dataclass(frozen=True, slots=True)
class SnapshotWindow:
    """Net stock decrease between the baseline export and the latest one."""

    key: str
    days: int
    label: str
    dropped_qty: int
    dropped_positions: int
    sku_ids: frozenset[int]
    unmatched: int
    baseline_on: date | None
    latest_on: date | None
    partial: bool


@dataclass(slots=True)
class SnapshotDropReport:
    """One row per window. Empty when fewer than two exports are stored."""

    windows: list[SnapshotWindow]

    def window(self, key: str) -> SnapshotWindow | None:
        """Return the card labelled ``key`` (``7``, ``30``, …)."""
        for row in self.windows:
            if row.key == key:
                return row
        return None


def _qty_maps() -> tuple[list[StockSnapshot], dict[int, dict[str, int]]]:
    snapshots = list(StockSnapshot.objects.order_by("taken_on"))
    maps: dict[int, dict[str, int]] = {snap.pk: {} for snap in snapshots}
    if not snapshots:
        return snapshots, maps
    for snapshot_id, key, qty, qty_ma in StockSnapshotLine.objects.filter(
        snapshot__in=snapshots,
    ).values_list("snapshot_id", "article_key", "qty", "qty_ma"):
        maps[snapshot_id][key] = int(qty or 0) + int(qty_ma or 0)
    return snapshots, maps


def build_snapshot_drop_report() -> SnapshotDropReport:
    """Compare each window with the latest stored export.

    The baseline is the newest export on or before ``latest - days``. When
    history does not reach that far, the oldest export is used and the window
    is marked partial.
    """
    snapshots, maps = _qty_maps()
    if len(snapshots) < 2:
        return SnapshotDropReport(windows=[])
    latest = snapshots[-1]
    latest_qty = maps[latest.pk]
    older = snapshots[:-1]
    windows: list[SnapshotWindow] = []
    for key, days, label in SNAPSHOT_WINDOWS:
        cutoff = latest.taken_on - timedelta(days=days)
        eligible = [snap for snap in older if snap.taken_on <= cutoff]
        partial = False
        if eligible:
            baseline = eligible[-1]
        else:
            baseline = older[0]
            partial = True
        base_qty = maps[baseline.pk]
        dropped: dict[str, int] = {}
        for article_key, old in base_qty.items():
            delta = old - latest_qty.get(article_key, 0)
            if delta > 0:
                dropped[article_key] = delta
        matched = sku_ids_by_stock_key(dropped)
        sku_ids: set[int] = set()
        unmatched = 0
        for article_key in dropped:
            ids = matched.get(article_key) or []
            if ids:
                sku_ids.update(ids)
            else:
                unmatched += 1
        windows.append(
            SnapshotWindow(
                key=key,
                days=days,
                label=label,
                dropped_qty=sum(dropped.values()),
                dropped_positions=len(dropped),
                sku_ids=frozenset(sku_ids),
                unmatched=unmatched,
                baseline_on=baseline.taken_on,
                latest_on=latest.taken_on,
                partial=partial,
            ),
        )
    return SnapshotDropReport(windows=windows)


def snapshot_report_for_request(request: HttpRequest) -> SnapshotDropReport:
    """Build the snapshot report once per changelist request."""
    cached = getattr(request, _REQUEST_CACHE, None)
    if isinstance(cached, SnapshotDropReport):
        return cached
    report = build_snapshot_drop_report()
    setattr(request, _REQUEST_CACHE, report)
    return report


def snapshot_drop_filter(request: HttpRequest) -> str | None:
    """Parse ``stock_drop=7|30|91|182|365``."""
    raw = (request.GET.get("stock_drop") or "").strip()
    if raw in _WINDOW_DAYS:
        return raw
    return None


def _fmt(day: date | None) -> str:
    if day is None:
        return ""
    return day.strftime("%d.%m.%Y")


def snapshot_template(request: HttpRequest) -> dict[str, Any]:
    """Template payload for the warehouse-export cards."""
    report = snapshot_report_for_request(request)
    base = reverse("admin:catalog_sku_changelist")
    selected = snapshot_drop_filter(request)
    windows: list[dict[str, Any]] = []
    for row in report.windows:
        windows.append(
            {
                "key": row.key,
                "label": row.label,
                "dropped_qty": row.dropped_qty,
                "dropped_positions": row.dropped_positions,
                "unmatched": row.unmatched,
                "baseline_on": _fmt(row.baseline_on),
                "latest_on": _fmt(row.latest_on),
                "partial": row.partial,
                "url": f"{base}?stock_drop={row.key}",
                "active": selected == row.key,
            },
        )
    return {
        "ready": bool(windows),
        "windows": windows,
        "filtering": selected is not None,
        "list_url": base,
    }
