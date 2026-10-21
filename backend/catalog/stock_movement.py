"""Stock movement cards for the SKU changelist.

Windows are rolling: 30 / 91 / 182 / 365 days. «В заказах» is the sum of
order lines in that window, cancelled orders excluded. Warehouse receipts
from 1C are not stored, so the cards do not show inbound movement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import Upper
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

# (months label, rolling window in days). 12 months matches a 365-day year.
PERIODS: tuple[tuple[int, int], ...] = (
    (1, 30),
    (3, 91),
    (6, 182),
    (12, 365),
)
_PERIOD_MONTHS = frozenset(months for months, _days in PERIODS)
_REQUEST_CACHE = "_hoocon_stock_movement"


@dataclass(frozen=True, slots=True)
class StockPeriod:
    """One rolling window of order movement versus stock sitting idle."""

    months: int
    days: int
    ordered_qty: int
    moved_positions: int
    idle_in_stock: int
    moved_ids: frozenset[int]
    idle_ids: frozenset[int]


@dataclass(slots=True)
class StockMovementReport:
    """Current on-hand total plus one row per period."""

    on_hand: int
    on_hand_positions: int
    periods: list[StockPeriod] = field(default_factory=list)
    include_orders: bool = True
    orders_scoped: bool = False

    def period(self, months: int) -> StockPeriod | None:
        """Return the window labelled ``months``, or None."""
        for row in self.periods:
            if row.months == months:
                return row
        return None


def build_stock_movement_report(
    *,
    now: datetime | None = None,
    include_orders: bool = True,
    user: Any | None = None,
) -> StockMovementReport:
    """Sum on-hand stock and order quantities for 1/3/6/12 months.

    Order lines follow ``scope_orders_for_manager`` for ``user``. No viewer
    yields no order lines. Admin, analyst, and superuser stay unscoped.

    Args:
        now: Clock for the rolling windows. Defaults to ``timezone.now()``.
        include_orders: When False, only the current stock totals are filled.
        user: Staff viewer. None counts no orders.

    Returns:
        Report with per-period order quantity, moved SKU ids and idle ids.
    """
    moment = now or timezone.now()
    stock = _on_hand()
    report = StockMovementReport(
        on_hand=stock[0],
        on_hand_positions=stock[1],
        include_orders=include_orders,
    )
    if not include_orders:
        return report

    from accounts.roles import staff_sees_all_leads

    report.orders_scoped = not staff_sees_all_leads(user)
    in_stock_ids = frozenset(
        _in_stock_ids(),
    )
    lines = _order_lines_since(moment - timedelta(days=PERIODS[-1][1]), user)
    for months, days in PERIODS:
        cutoff = moment - timedelta(days=days)
        qty = 0
        moved: set[int] = set()
        for sku_id, created_at, quantity in lines:
            if created_at < cutoff:
                continue
            qty += quantity
            if sku_id is not None:
                moved.add(sku_id)
        moved_ids = frozenset(moved)
        idle_ids = in_stock_ids - moved_ids
        report.periods.append(
            StockPeriod(
                months=months,
                days=days,
                ordered_qty=qty,
                moved_positions=len(moved_ids),
                idle_in_stock=len(idle_ids),
                moved_ids=moved_ids,
                idle_ids=idle_ids,
            ),
        )
    return report


def stock_report_for_request(request: HttpRequest) -> StockMovementReport:
    """Build the report once per request.

    Orders require ``cabinet.view_order`` and the same client scope as the
    order changelist (``scope_orders_for_manager``).
    """
    cached = getattr(request, _REQUEST_CACHE, None)
    if isinstance(cached, StockMovementReport):
        return cached
    user = getattr(request, "user", None)
    include_orders = bool(user and user.has_perm("cabinet.view_order"))
    report = build_stock_movement_report(include_orders=include_orders, user=user)
    setattr(request, _REQUEST_CACHE, report)
    return report


def movement_filter(request: HttpRequest) -> tuple[str, int] | None:
    """Parse ``stock_flow=move-3`` or ``stock_flow=idle-12``."""
    raw = (request.GET.get("stock_flow") or "").strip()
    mode, _, months_raw = raw.partition("-")
    if mode in {"move", "idle"} and months_raw.isdigit() and int(months_raw) in _PERIOD_MONTHS:
        return mode, int(months_raw)
    return None


def movement_template(report: StockMovementReport, request: HttpRequest) -> dict[str, Any]:
    """Template payload: totals, period cards, and which card is filtering the list."""
    base = reverse("admin:catalog_sku_changelist")
    selected = movement_filter(request)
    periods: list[dict[str, Any]] = []
    for row in report.periods:
        periods.append(
            {
                "months": row.months,
                "days": row.days,
                "ordered_qty": row.ordered_qty,
                "moved_positions": row.moved_positions,
                "idle_in_stock": row.idle_in_stock,
                "move_url": f"{base}?stock_flow=move-{row.months}",
                "idle_url": f"{base}?stock_flow=idle-{row.months}",
                "move_active": selected == ("move", row.months),
                "idle_active": selected == ("idle", row.months),
            },
        )
    return {
        "on_hand": report.on_hand,
        "on_hand_positions": report.on_hand_positions,
        "include_orders": report.include_orders,
        "orders_scoped": report.orders_scoped,
        "periods": periods,
        "list_url": base,
        "filtering": selected is not None,
    }


def _on_hand() -> tuple[int, int]:
    from catalog.models import SKU

    row = SKU.objects.aggregate(
        qty=Sum("stock_qty"),
        ma=Sum("stock_qty_ma"),
        positions=Count("id", filter=Q(stock_qty__gt=0) | Q(stock_qty_ma__gt=0)),
    )
    total = int(row["qty"] or 0) + int(row["ma"] or 0)
    return total, int(row["positions"] or 0)


def _in_stock_ids() -> list[int]:
    from catalog.models import SKU

    return list(
        SKU.objects.filter(Q(stock_qty__gt=0) | Q(stock_qty_ma__gt=0)).values_list("id", flat=True),
    )


def _order_lines_since(cutoff: datetime, user: Any | None) -> list[tuple[int | None, datetime, int]]:
    """Non-cancelled order lines since ``cutoff`` as ``(sku_id, created_at, qty)``.

    Lines are limited to orders ``user`` may open. A line whose SKU link was
    cleared is attached by article code when that code still exists in the catalog.
    """
    from cabinet.models import Order, OrderItem, OrderStatus
    from crm.services import scope_orders_for_manager

    visible = scope_orders_for_manager(Order.objects.all(), user)
    rows = list(
        OrderItem.objects.filter(order__in=visible.filter(created_at__gte=cutoff))
        .exclude(order__status=OrderStatus.CANCELLED)
        .values_list("sku_id", "sku_code", "quantity", "order__created_at"),
    )
    unresolved = {
        (code or "").strip().upper() for sku_id, code, _qty, _at in rows if sku_id is None and (code or "").strip()
    }
    by_code: dict[str, int] = {}
    if unresolved:
        from catalog.models import SKU

        by_code = {
            code: sku_id
            for code, sku_id in SKU.objects.annotate(code_upper=Upper("sku_code"))
            .filter(code_upper__in=unresolved)
            .values_list("code_upper", "id")
        }
    lines: list[tuple[int | None, datetime, int]] = []
    for sku_id, code, quantity, created_at in rows:
        resolved = sku_id
        if resolved is None:
            resolved = by_code.get((code or "").strip().upper())
        lines.append((resolved, created_at, int(quantity or 0)))
    return lines
