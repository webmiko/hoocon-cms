#!/usr/bin/env python3
"""Build yearly stock/sales Wiki dashboard HTML from 1C monthly XLSX exports."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "backend/content/fixtures/wiki/stock-dashboard-14-09-2026.html"
DEFAULT_OUTPUT = ROOT / "backend/content/fixtures/wiki/stock-dashboard-year-2025-09-2026-08.html"

MONTH_FILES: tuple[tuple[str, str, int], ...] = (
    ("2025-09", "Сентябрь 2025.xlsx", 30),
    ("2025-10", "Октябрь 2025.xlsx", 31),
    ("2025-11", "Ноябрь 2025.xlsx", 30),
    ("2025-12", "Декабрь 2025.xlsx", 31),
    ("2026-01", "Январь 2026.xlsx", 31),
    ("2026-02", "Февраль 2026.xlsx", 28),
    ("2026-03", "Март 2026.xlsx", 31),
    ("2026-04", "Апрель 2026.xlsx", 30),
    ("2026-05", "Май 2026.xlsx", 31),
    ("2026-06", "Июнь 2026.xlsx", 30),
    ("2026-07", "Июль 2026.xlsx", 31),
    ("2026-08", "Август 2026.xlsx", 31),
)

STOCK_SNAPSHOT = "Остатки товаров на 14 сентября 2026.xlsx"
PERIOD_START = date(2025, 9, 1)
PERIOD_END = date(2026, 8, 31)
PERIOD_DAYS = 365
SNAPSHOT_DATE = date(2026, 9, 14)
TARGET_DAYS = 60


def _num(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _series_key(sku: str) -> str:
    if sku.startswith("BR"):
        return "BR"
    if sku.startswith("HVD"):
        return "HVD"
    if sku.startswith("HVA"):
        return "HVA"
    for prefix in ("DA", "SA", "BV"):
        if sku.startswith(prefix):
            return prefix
    return sku.split("-")[0][:4] if "-" in sku else sku[:4]


def _classify_idle(sku: str, name: str, stock: int) -> str:
    upper_name = name.upper()
    if sku.startswith("BV"):
        return "Краны BV"
    if "24" in sku or "24В" in upper_name or "24V" in upper_name:
        return "Исполнение 24В"
    if "MU" in sku:
        return "MU без движения"
    if sku.startswith("HVA") or sku.startswith("HVD"):
        return "Серия HVA/HVD"
    if sku.endswith("-D") or sku.endswith("-A") or "-AS" in sku:
        return "Плавное / D / A исполнение"
    if stock >= 100:
        return "Крупный остаток (≥100)"
    if stock <= 5:
        return "Малый остаток (≤5)"
    return "Прочие DA/SA"


CATEGORY_META: dict[str, dict[str, str]] = {
    "Краны BV": {
        "meaning": (
            "Шаровые краны DN15–DN150. Продаются под комплекты «кран + привод» "
            "или проектно, не потоком."
        ),
        "action": (
            "Не пополнять без заявок. Крупные DN — замороженный капитал, не дефицит."
        ),
    },
    "Исполнение 24В": {
        "meaning": (
            "Приводы на 24В для BMS/автоматики. Отдельный канал сбыта от 230В."
        ),
        "action": "Стратегия через интеграторов. Не смешивать с закупкой 230В ходовых.",
    },
    "Плавное / D / A исполнение": {
        "meaning": (
            "Модулирующее управление и исполнения D/A. Спрос есть, но в разы меньше ON/OFF."
        ),
        "action": "Минимальный страховой запас. Пополнение — под заказ.",
    },
    "Серия HVA/HVD": {
        "meaning": "Параллельная линейка HV. Другой сегмент, не DA/SA.",
        "action": "Проверить активность в CRM. Без спроса — не расширять запас.",
    },
    "MU без движения": {
        "meaning": "Нишевые моменты MU. Рядом AS-версии тоже могут стоять без движения.",
        "action": "Уточнить: нет спроса на момент или SKU не в активных продажах.",
    },
    "Крупный остаток (≥100)": {
        "meaning": "Много на складе, ноль отгрузок за год. Возможна каннибализация суффиксов.",
        "action": "Сверить с реальными заявками и активными карточками на сайте.",
    },
    "Малый остаток (≤5)": {
        "meaning": "Почти пустая полка. Не «не продаётся», а «почти нет для отгрузки».",
        "action": "Довести до минимума или точечно пополнить под заказ.",
    },
    "Прочие DA/SA": {
        "meaning": "Единичные SKU без движения вне основных групп.",
        "action": "Разбор вручную по истории заявок.",
    },
}


@dataclass
class MonthRow:
    label: str
    key: str
    days: int
    warehouse_start: int = 0
    warehouse_end: int = 0
    warehouse_sales: int = 0
    warehouse_receipts: int = 0
    items: dict[str, dict[str, int]] = field(default_factory=dict)


def _column_map(headers: tuple[object, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, header in enumerate(headers):
        text = str(header or "").strip()
        if text == "Начало":
            mapping["start"] = idx
        elif text == "Поступление от поставщика":
            mapping["receipts"] = idx
        elif text == "Расход":
            mapping["expense"] = idx
        elif text == "Продажа покупателю":
            mapping["sales"] = idx
        elif text == "Конец":
            mapping["end"] = idx
    return mapping


def _parse_monthly(path: Path, label: str, key: str, days: int) -> MonthRow:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    cols = _column_map(headers)
    row = MonthRow(label=label, key=key, days=days)

    skip_names = {"основной склад", "итого", "номенклатура"}

    for raw in ws.iter_rows(min_row=3, values_only=True):
        name = str(raw[0] or "").strip()
        if not name:
            continue
        if name.lower() in skip_names:
            row.warehouse_start = _num(raw[cols["start"]])
            row.warehouse_end = _num(raw[cols["end"]])
            row.warehouse_sales = _num(raw[cols["sales"]])
            if "receipts" in cols:
                row.warehouse_receipts = _num(raw[cols["receipts"]])
            continue

        row.items[name] = {
            "start": _num(raw[cols["start"]]),
            "sales": _num(raw[cols["sales"]]),
            "end": _num(raw[cols["end"]]),
            "receipts": _num(raw[cols["receipts"]]) if "receipts" in cols else 0,
        }
    wb.close()
    return row


def _parse_stock_snapshot(path: Path) -> dict[str, dict[str, object]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    items: dict[str, dict[str, object]] = {}
    for raw in ws.iter_rows(min_row=2, values_only=True):
        name = str(raw[0] or "").strip()
        sku = str(raw[3] or "").strip()
        if not sku:
            continue
        items[sku] = {
            "name": name,
            "stock": _num(raw[1]),
        }
    wb.close()
    return items


def _build_name_index(
    months: list[MonthRow],
    snapshot: dict[str, dict[str, object]],
) -> dict[str, str]:
    by_norm: dict[str, str] = {}
    for sku, meta in snapshot.items():
        by_norm[_norm_name(str(meta["name"]))] = sku

    for month in months:
        for name in month.items:
            norm = _norm_name(name)
            if norm in by_norm:
                continue
            token = name.split()[0]
            if token in snapshot:
                by_norm[norm] = token
    return by_norm


def _resolve_sku(name: str, name_index: dict[str, str], snapshot: dict[str, object]) -> str:
    norm = _norm_name(name)
    if norm in name_index:
        return name_index[norm]
    token = name.split()[0]
    if token in snapshot:
        return token
    return token


def _priority(stock: int, days_left: int, order: int, sold: int) -> str:
    if sold <= 0:
        return "OK"
    if stock == 0 or days_left <= 14:
        return "P1"
    if order > 0:
        return "P3"
    return "OK"


def build_payload(source_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    months = [
        _parse_monthly(source_dir / filename, Path(filename).stem, key, days)
        for key, filename, days in MONTH_FILES
    ]
    snapshot = _parse_stock_snapshot(source_dir / STOCK_SNAPSHOT)
    name_index = _build_name_index(months, snapshot)

    sku_names: dict[str, str] = {sku: str(meta["name"]) for sku, meta in snapshot.items()}
    monthly_sales: dict[str, list[int]] = defaultdict(lambda: [0] * len(months))
    monthly_end: dict[str, list[int | None]] = defaultdict(lambda: [None] * len(months))
    yearly_sales: dict[str, int] = defaultdict(int)
    yearly_receipts: dict[str, int] = defaultdict(int)

    for month_idx, month in enumerate(months):
        for name, values in month.items.items():
            sku = _resolve_sku(name, name_index, snapshot)
            sku_names.setdefault(sku, name)
            monthly_sales[sku][month_idx] += values["sales"]
            monthly_end[sku][month_idx] = values["end"]
            yearly_sales[sku] += values["sales"]
            yearly_receipts[sku] += values["receipts"]

    all_skus = set(sku_names) | set(yearly_sales)

    month_labels = [m.label for m in months]
    month_short = [m.key[5:7] + "." + m.key[2:4] for m in months]
    stock_totals = [m.warehouse_end for m in months]
    positions = [len(m.items) for m in months]

    total_sold = sum(m.warehouse_sales for m in months)
    avg_daily = round(total_sold / PERIOD_DAYS, 1)

    periods = []
    for month in months:
        periods.append(
            {
                "label": month.label,
                "days": month.days,
                "sold": month.warehouse_sales,
                "daily": round(month.warehouse_sales / month.days, 1),
                "items": sum(1 for item in month.items.values() if item["sales"] > 0),
                "stock_end": month.warehouse_end,
                "receipts": month.warehouse_receipts,
            }
        )

    series_stats: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"sold": 0, "stock": 0, "order": 0}
    )
    top_rows: list[dict[str, Any]] = []
    idle_items: list[dict[str, Any]] = []

    def _history_values(sku: str) -> list[int]:
        values = monthly_end.get(sku, [None] * len(months))
        filled: list[int] = []
        last = 0
        for value in values:
            if value is not None:
                last = value
            filled.append(last)
        return filled

    for sku in sorted(all_skus):
        sold = yearly_sales.get(sku, 0)
        if sku in snapshot:
            stock = _num(snapshot[sku]["stock"])
            name = str(snapshot[sku]["name"])
        else:
            stock = 0
            name = sku_names.get(sku, sku)
        daily = round(sold / PERIOD_DAYS, 1) if sold else 0.0
        days_left = round(stock / daily) if daily > 0 else (0 if stock == 0 else 9999)
        order = max(0, int(round(daily * TARGET_DAYS - stock))) if daily > 0 else 0
        priority = _priority(stock, days_left, order, sold)
        history = _history_values(sku)
        series = _series_key(sku)
        series_stats[series]["sold"] += sold
        series_stats[series]["stock"] += stock
        series_stats[series]["order"] += order

        if sold > 0:
            top_rows.append(
                {
                    "sku": sku,
                    "name": name,
                    "sold": sold,
                    "daily": daily,
                    "stock": stock,
                    "days_left": days_left,
                    "order": order,
                    "priority": priority,
                    "history": history,
                }
            )
        elif stock > 0:
            idle_items.append(
                {
                    "sku": sku,
                    "name": name,
                    "category": _classify_idle(sku, name, stock),
                    "series": series,
                    "stock": stock,
                    "history": history,
                }
            )

    top_rows.sort(key=lambda row: row["sold"], reverse=True)
    top_sold = top_rows[:15]

    series_rows = []
    for series, stats in sorted(series_stats.items(), key=lambda item: item[1]["sold"], reverse=True):
        sold = int(stats["sold"])
        stock = int(stats["stock"])
        daily = round(sold / PERIOD_DAYS, 1) if sold else 0.0
        days = round(stock / daily) if daily > 0 else 9999
        series_rows.append(
            {
                "series": series,
                "sold": sold,
                "stock": stock,
                "daily": daily,
                "order": int(stats["order"]),
                "days": days,
            }
        )

    p1 = [
        {
            "sku": row["sku"],
            "name": row["name"],
            "stock": row["stock"],
            "daily": row["daily"],
            "days_left": row["days_left"],
            "order": row["order"],
        }
        for row in top_rows
        if row["priority"] == "P1" and row["order"] > 0
    ]
    p1.sort(key=lambda row: row["order"], reverse=True)

    priorities: dict[str, dict[str, int]] = {
        "OK": {"count": 0, "sold": 0, "order": 0},
        "P1": {"count": 0, "sold": 0, "order": 0},
        "P2": {"count": 0, "sold": 0, "order": 0},
        "P3": {"count": 0, "sold": 0, "order": 0},
    }
    for row in top_rows:
        bucket = priorities[row["priority"]]
        bucket["count"] += 1
        bucket["sold"] += row["sold"]
        bucket["order"] += row["order"]

    out_of_stock = sum(1 for sku, meta in snapshot.items() if _num(meta["stock"]) == 0)
    low_stock = sum(
        1
        for row in top_rows
        if row["stock"] > 0 and row["days_left"] <= 14 and row["daily"] > 0
    )
    total_order = sum(row["order"] for row in top_rows)

    stock_start = months[0].warehouse_start
    stock_end = stock_totals[-1]
    stock_delta = stock_end - stock_start
    stock_delta_pct = round(stock_delta / stock_start * 100, 1) if stock_start else 0.0

    peak_month = max(periods, key=lambda row: row["sold"])
    low_month = min(periods, key=lambda row: row["sold"])
    da_sa_share = 0.0
    if total_sold:
        da_sa_share = round(
            sum(row["sold"] for row in series_rows if row["series"] in {"DA", "SA"}) / total_sold * 100,
            1,
        )

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "stock": 0})
    for item in idle_items:
        bucket = by_category[item["category"]]
        bucket["count"] += 1
        bucket["stock"] += item["stock"]

    exception = None
    for sku, receipts in yearly_receipts.items():
        if receipts > 0 and yearly_sales.get(sku, 0) == 0 and sku in snapshot:
            exception = {
                "sku": sku,
                "history": monthly_end.get(sku, [0] * len(months)),
                "note": f"Чистый расход 0 за год, но было поступление +{receipts} шт.",
            }
            break

    narrative = [
        {
            "title": f"{total_sold:,} шт за год (~{avg_daily} шт/день)".replace(",", " "),
            "body": (
                "Это <strong>продажи покупателям</strong> по месячным отчётам 1С, "
                f"не заказы с сайта. Пик — <strong>{peak_month['label']}</strong> "
                f"({peak_month['sold']:,} шт), минимум — <strong>{low_month['label']}</strong> "
                f"({low_month['sold']:,} шт)."
            ).replace(",", " "),
        },
        {
            "title": (
                f"{stock_delta:+,} шт ({stock_delta_pct:+.1f}%) на складе за год"
            ).replace(",", " "),
            "body": (
                f"Остаток склада: <strong>{stock_start:,}</strong> → "
                f"<strong>{stock_end:,}</strong> шт (конец августа). "
                f"Снимок на <strong>{SNAPSHOT_DATE:%d.%m.%Y}</strong> — отдельно в плане пополнения."
            ).replace(",", " "),
        },
        {
            "title": f"DA + SA = {da_sa_share}% годового расхода",
            "body": (
                "<strong>DA</strong> — массовые воздушные ON/OFF. "
                "<strong>SA</strong> — пожарка/дымоудаление. "
                "<strong>BR</strong> — расходник к монтажу."
            ),
        },
        {
            "title": f"Топ SKU: {top_sold[0]['sku']} — {top_sold[0]['sold']} шт",
            "body": (
                f"Лидер года — <strong>{top_sold[0]['sku']}</strong>. "
                f"Второй — <strong>{top_sold[1]['sku']}</strong> "
                f"({top_sold[1]['sold']} шт)."
            ),
        },
        {
            "title": f"P1 — {len(p1)} позиций, заказ {sum(row['order'] for row in p1):,} шт".replace(",", " "),
            "body": (
                "По снимку <strong>14.09.2026</strong> и годовой скорости "
                f"(цель {TARGET_DAYS} дней запаса). Срочные позиции — в таблице P1."
            ),
        },
        {
            "title": f"{len(idle_items)} позиций без продаж за год",
            "body": (
                f"Суммарно <strong>{sum(item['stock'] for item in idle_items):,} шт</strong> "
                "на складе без движения в отчётах — см. раздел «без движения»."
            ).replace(",", " "),
        },
    ]

    data = {
        "period_start": PERIOD_START.strftime("%d.%m.%Y"),
        "period_end": PERIOD_END.strftime("%d.%m.%Y"),
        "period_days": PERIOD_DAYS,
        "snapshot_date": SNAPSHOT_DATE.strftime("%d.%m.%Y"),
        "date_labels": month_labels,
        "date_cols": month_short,
        "stock_totals": stock_totals,
        "positions": positions,
        "total_sold": total_sold,
        "avg_daily": avg_daily,
        "total_order": total_order,
        "periods": periods,
        "series": series_rows,
        "top_sold": top_sold,
        "p1": p1,
        "priorities": priorities,
        "out_of_stock_count": out_of_stock,
        "low_stock_count": low_stock,
        "unchanged": len(idle_items),
        "unchanged_zero_net": len(idle_items),
        "declined": sum(1 for row in top_rows if row["sold"] > 0),
        "stock_delta": stock_delta,
        "stock_delta_pct": stock_delta_pct,
        "snapshot_stock_total": sum(_num(meta["stock"]) for meta in snapshot.values()),
        "snapshot_positions": len(snapshot),
    }

    insights = {
        "count_stable": len(idle_items),
        "count_zero_net": len(idle_items),
        "stock_total": sum(item["stock"] for item in idle_items),
        "by_category": [
            {"category": key, "count": value["count"], "stock": value["stock"]}
            for key, value in sorted(by_category.items(), key=lambda item: item[1]["stock"], reverse=True)
        ],
        "category_meta": CATEGORY_META,
        "exception": exception
        or {
            "sku": "—",
            "history": [0] * len(months),
            "note": "Явных поставок без продаж за год не выделено.",
        },
        "narrative": narrative,
        "items": sorted(idle_items, key=lambda item: item["stock"], reverse=True),
    }
    return data, insights


def _replace_json_block(text: str, marker: str, payload: dict[str, Any]) -> str:
    start = text.index(marker) + len(marker)
    depth = 0
    end = start
    for idx, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break
    pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    return text[: start - len(marker)] + marker + pretty + text[end:]


def render_html(data: dict[str, Any], insights: dict[str, Any], generated: date) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    html = template

    html = html.replace(
        "<title>Hoocon — Анализ остатков и продаж · 10.08–14.09.2026</title>",
        "<title>Hoocon — Анализ остатков и продаж · сен 2025 — авг 2026</title>",
    )
    html = html.replace(
        "<h1>Анализ остатков и продаж Hoocon</h1>",
        "<h1>Анализ остатков и продаж Hoocon · год</h1>",
    )
    html = html.replace(
        "<p class=\"sub\">Период: 10.08.2026 — 14.09.2026 · 4 снимка склада · 35 дней</p>",
        (
            "<p class=\"sub\">Период: 01.09.2025 — 31.08.2026 · 12 месячных отчётов 1С · "
            f"снимок остатков {data['snapshot_date']}</p>"
        ),
    )
    html = html.replace(
        "Цифры — это <strong>изменение свободных остатков</strong> между 4 снимками склада "
        "(10.08, 24.08, 07.09, 14.09).",
        (
            "Цифры — это <strong>продажи покупателям</strong> и остатки по "
            "месячным отчётам 1С (сентябрь 2025 — август 2026). План пополнения — "
            f"по снимку <strong>{data['snapshot_date']}</strong>."
        ),
    )
    html = html.replace(
        "<h2 class=\"section-title\">Динамика склада и продаж</h2>",
        "<h2 class=\"section-title\">Динамика склада и продаж по месяцам</h2>",
    )
    html = html.replace(
        "Сравнение суммарных остатков по датам снимков и объёма «продаж» (списаний/отгрузок)\n"
        "        между снимками. Снижение остатков без пополнений интерпретируется как расход.",
        (
            "Суммарные остатки склада на конец каждого месяца и объём продаж покупателям. "
            "Столбцы «шт/день» — средний темп месяца."
        ),
    )
    html = html.replace(
        "<h3>Остатки на складе (шт, все позиции)</h3>",
        "<h3>Остаток склада на конец месяца (шт)</h3>",
    )
    html = html.replace(
        "<h3>Продажи по интервалам (шт/день)</h3>",
        "<h3>Продажи по месяцам (шт и шт/день)</h3>",
    )
    html = html.replace(
        "<h3>Остаток vs продано (по сериям)</h3>",
        f"<h3>Остаток {data['snapshot_date']} vs продано за год (по сериям)</h3>",
    )
    html = html.replace(
        "<h2 class=\"section-title\">Ходовой товар — топ-15</h2>",
        "<h2 class=\"section-title\">Ходовой товар за год — топ-15</h2>",
    )
    html = html.replace(
        "Позиции с наибольшим расходом за 35 дней. Красным отмечены SKU с запасом ≤14 дней\n"
        "        или нулевым остатком.",
        (
            "Позиции с наибольшими продажами за 12 месяцев. Красным — SKU с запасом ≤14 дней "
            f"или нулём на {data['snapshot_date']}."
        ),
    )
    html = html.replace(
        "<h2 class=\"section-title\">Траектория остатков — критичные SKU</h2>",
        "<h2 class=\"section-title\">Траектория остатков P1 — помесячно</h2>",
    )
    html = html.replace(
        "Как менялись остатки у позиций, требующих срочного пополнения (P1).",
        "Конец месяца по позициям P1 (по снимку 14.09 — отдельная таблица заказа).",
    )
    html = html.replace(
        "<h2 class=\"section-title\">Позиции без движения за период</h2>",
        "<h2 class=\"section-title\">Позиции без продаж за год</h2>",
    )
    html = html.replace(
        "<h2 class=\"section-title\">План пополнения (цель: 60 дней запаса)</h2>",
        "<h2 class=\"section-title\">План пополнения на снимке 14.09 (цель: 60 дней)</h2>",
    )
    html = html.replace(
        "Расчёт: средняя скорость за 35 дней × 60 − текущий остаток.",
        "Расчёт: годовая скорость (продажи / 365) × 60 − остаток на снимке.",
    )
    html = html.replace(
        "<h2 class=\"section-title\">Сводная таблица — топ-15 ходовых</h2>",
        "<h2 class=\"section-title\">Сводная таблица — топ-15 за год</h2>",
    )
    html = html.replace(
        "Немедленно</h3>\n          <ul style=\"padding-left:1.2rem; color:var(--muted); font-size:0.9rem;\">\n"
        "            <li style=\"margin-bottom:0.5rem;\"><strong style=\"color:var(--text)\">DA5FU230-DS</strong> — 930 шт (обнулён, 15,5/день)</li>\n"
        "            <li style=\"margin-bottom:0.5rem;\"><strong style=\"color:var(--text)\">SA5FU230-DS</strong> — 719 шт (43 шт, ~3 дня)</li>\n"
        "            <li><strong style=\"color:var(--text)\">Итого P1:</strong> 2 187 шт · 94% — 6 позиций</li>\n"
        "          </ul>",
        "Немедленно</h3>\n          <ul id=\"recs-p1\" style=\"padding-left:1.2rem; color:var(--muted); font-size:0.9rem;\"></ul>",
    )
    html = html.replace(
        "На этой неделе</h3>\n          <ul style=\"padding-left:1.2rem; color:var(--muted); font-size:0.9rem;\">\n"
        "            <li style=\"margin-bottom:0.5rem;\">DA16MQU230-DS — 270 шт (24 шт, 5 дней)</li>\n"
        "            <li style=\"margin-bottom:0.5rem;\">DA8MQU230-DS — 94 шт · BV232B — 96 шт · DA6MU24-A — 78 шт</li>\n"
        "            <li>BR-M, SA10MU230-DS — запас 130–260 дней, заказ не срочен</li>\n"
        "          </ul>",
        (
            "На этой неделе</h3>\n          <ul style=\"padding-left:1.2rem; color:var(--muted); "
            "font-size:0.9rem;\">\n            <li>См. таблицу P1 и топ-15 — приоритет по "
            "остатку на 14.09 и годовой скорости.</li>\n          </ul>"
        ),
    )
    html = html.replace(
        "Источник: выгрузки «Остатки товаров» 10.08, 24.08, 07.09, 14.09.2026 ·\n"
        "    Сгенерировано 14.09.2026 · Hoocon CMS",
        (
            "Источник: месячные отчёты 1С сен 2025 — авг 2026 + снимок остатков "
            f"{data['snapshot_date']} · Сгенерировано {generated:%d.%m.%Y} · Hoocon CMS"
        ),
    )

    html = _replace_json_block(html, "const DATA = ", data)
    html = _replace_json_block(html, "const INSIGHTS = ", insights)

    html = html.replace(
        "labels: DATA.date_labels.map(l => isMobile() ? l.slice(0, 5) : l),",
        "labels: DATA.date_cols.map(l => isMobile() ? l : l),",
    )
    html = html.replace(
        "<div class=\"kpi\"><div class=\"label\">Остаток 14.09</div><div class=\"value\">${fmt(DATA.stock_totals[3])}</div><div class=\"hint\">${DATA.positions[3]} позиций</div></div>",
        (
            "<div class=\"kpi\"><div class=\"label\">Остаток ${DATA.snapshot_date}</div>"
            "<div class=\"value\">${fmt(DATA.snapshot_stock_total)}</div>"
            "<div class=\"hint\">${DATA.snapshot_positions} позиций</div></div>"
        ),
    )
    html = html.replace(
        "<div class=\"kpi yellow\"><div class=\"label\">Списание за период</div><div class=\"value\">−${fmt(DATA.stock_totals[0] - DATA.stock_totals[3])}</div><div class=\"hint\">−11,8% от старта</div></div>",
        (
            "<div class=\"kpi yellow\"><div class=\"label\">Δ склада за год</div>"
            "<div class=\"value\">${DATA.stock_delta >= 0 ? '+' : ''}${fmt(DATA.stock_delta)}</div>"
            "<div class=\"hint\">${DATA.stock_delta_pct >= 0 ? '+' : ''}${DATA.stock_delta_pct}% "
            "авг к сен</div></div>"
        ),
    )
    html = html.replace(
        "{ label: 'Остаток 14.09', data: DATA.series.map(s => s.stock), backgroundColor: '#22c55e', borderRadius: 4 }",
        "{ label: 'Остаток ' + DATA.snapshot_date, data: DATA.series.map(s => s.stock), backgroundColor: '#22c55e', borderRadius: 4 }",
    )
    html = html.replace(
        "datasets: [{ label: 'Продано за 35 дней', data: DATA.top_sold.map(t => t.sold), backgroundColor: topColors, borderRadius: 4 }]",
        "datasets: [{ label: 'Продано за год', data: DATA.top_sold.map(t => t.sold), backgroundColor: topColors, borderRadius: 4 }]",
    )
    html = html.replace(
        "`<strong>${INSIGHTS.count_stable} позиций</strong> с одинаковым остатком во всех 4 снимках `",
        "`<strong>${INSIGHTS.count_stable} позиций</strong> без продаж за год `",
    )
    html = html.replace(
        "+ `(суммарно <strong>${fmt(INSIGHTS.stock_total)} шт</strong>, ~18% склада). `",
        "+ `(суммарно <strong>${fmt(INSIGHTS.stock_total)} шт</strong> на складе). `",
    )
    html = html.replace(
        "renderIdleList();\n\n    let resizeTimer;",
        (
            "renderIdleList();\n\n    const recs = document.getElementById('recs-p1');\n"
            "    if (recs && DATA.p1.length) {\n"
            "      const top = DATA.p1.slice(0, 3).map(p =>\n"
            "        `<li style=\"margin-bottom:0.5rem;\"><strong style=\"color:var(--text)\">"
            "${p.sku}</strong> — ${fmt(p.order)} шт (${p.stock} шт, ${p.days_left} дн)</li>`\n"
            "      ).join('');\n"
            "      const total = DATA.p1.reduce((s, p) => s + p.order, 0);\n"
            "      recs.innerHTML = top + `<li><strong style=\"color:var(--text)\">Итого P1:</strong> "
            "${fmt(total)} шт · ${DATA.p1.length} поз.</li>`;\n"
            "    }\n\n    let resizeTimer;"
        ),
    )

    # Remove hardcoded insight boxes tied to the short-period dashboard.
    html = re.sub(
        r'<div class="insight">\s*<strong>−4 190 шт.*?</div>\s*',
        '<div class="insight" id="insight-stock"></div>\n          ',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<div class="insight warn">\s*Темп замедляется.*?</div>\s*',
        '<div class="insight warn" id="insight-periods"></div>\n          ',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<div class="insight">\s*DA: запас.*?</div>\s*',
        '<div class="insight" id="insight-series"></div>\n          ',
        html,
        count=1,
        flags=re.S,
    )
    html = re.sub(
        r'<div class="insight danger">\s*<strong>DA5FU230-DS</strong>.*?</div>\s*',
        "",
        html,
        count=1,
        flags=re.S,
    )
    html = html.replace(
        "renderIdleList();\n\n    const recs = document.getElementById('recs-p1');",
        (
            "document.getElementById('insight-stock').innerHTML =\n"
            "      `<strong>${DATA.stock_delta >= 0 ? '+' : ''}${fmt(DATA.stock_delta)} шт "
            "(${DATA.stock_delta_pct >= 0 ? '+' : ''}${DATA.stock_delta_pct}%)</strong> "
            "между концом сен 2025 и авг 2026.`;\n"
            "    const peak = DATA.periods.reduce((a, b) => (b.sold > a.sold ? b : a), DATA.periods[0]);\n"
            "    const low = DATA.periods.reduce((a, b) => (b.sold < a.sold ? b : a), DATA.periods[0]);\n"
            "    document.getElementById('insight-periods').innerHTML =\n"
            "      `Пик <strong>${peak.label}</strong> (${fmt(peak.sold)} шт, ${peak.daily}/день). "
            "Минимум <strong>${low.label}</strong> (${fmt(low.sold)} шт).`;\n"
            "    const da = DATA.series.find(s => s.series === 'DA');\n"
            "    const sa = DATA.series.find(s => s.series === 'SA');\n"
            "    document.getElementById('insight-series').innerHTML =\n"
            "      `DA: ~${da ? da.days : '—'} дн запаса · SA: ~${sa ? sa.days : '—'} дн "
            "при годовой скорости.`;\n\n"
            "    renderIdleList();\n\n    const recs = document.getElementById('recs-p1');"
        ),
    )

    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source_dir",
        nargs="?",
        default="/Users/niko/Downloads/2026-09",
        help="Directory with monthly XLSX exports",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output HTML path",
    )
    args = parser.parse_args()
    source_dir = Path(args.source_dir)
    data, insights = build_payload(source_dir)
    html = render_html(data, insights, date.today())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({len(html):,} bytes)")
    print(f"Total sold: {data['total_sold']:,} · P1 items: {len(data['p1'])}")


if __name__ == "__main__":
    main()
