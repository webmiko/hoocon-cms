#!/usr/bin/env python3
"""Статистика минут GitHub Actions (условный бюджет 2000/мес → 500/нед).

Репо public — GH-hosted минуты не списываются с личного бюджета; скрипт
для темпа CI и сценария private/self-hosted. Оценка — сумма длительностей
job'ов за календарный месяц (Linux = 1×). Для private: ``--set-used N``
из Settings → Billing → Actions.

Usage:
  ./scripts/actions-minutes.py
  ./scripts/actions-minutes.py --refresh
  ./scripts/actions-minutes.py --set-used 420
  ./scripts/actions-minutes.py --json
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

MONTHLY_FREE_MINUTES = 2000
WEEKS_PER_MONTH = 4
WEEKLY_BUDGET_MINUTES = MONTHLY_FREE_MINUTES // WEEKS_PER_MONTH  # 500

ROOT = Path(
    subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
    ).strip(),
)
STATE_DIR = ROOT / ".local"
STATE_PATH = STATE_DIR / "actions-minutes.json"


@dataclass(frozen=True)
class Period:
    """Календарный месяц и текущая неделя (1–4) внутри него."""

    year: int
    month: int
    week: int
    week_start: date
    week_end: date
    month_start: date
    month_end: date

    @classmethod
    def for_day(cls, today: date) -> Period:
        """Построить период для дня ``today`` (UTC-календарь)."""
        month_start = today.replace(day=1)
        if today.month == 12:
            next_month = date(today.year + 1, 1, 1)
        else:
            next_month = date(today.year, today.month + 1, 1)
        month_end = next_month - timedelta(days=1)

        # Дни 1–7 → неделя 1; 8–14 → 2; 15–21 → 3; 22–конец месяца → 4.
        week = min(WEEKS_PER_MONTH, (today.day - 1) // 7 + 1)
        week_start = month_start + timedelta(days=(week - 1) * 7)
        if week < WEEKS_PER_MONTH:
            week_end = week_start + timedelta(days=6)
        else:
            week_end = month_end
        return cls(
            year=today.year,
            month=today.month,
            week=week,
            week_start=week_start,
            week_end=week_end,
            month_start=month_start,
            month_end=month_end,
        )


def _gh_json(args: list[str]) -> Any:
    """Вызвать ``gh`` и разобрать JSON; при ошибке — понятный exit."""
    cmd = ["gh", *args]
    try:
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
    except FileNotFoundError:
        print("gh CLI не найден. Установи: https://cli.github.com/", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "").strip() or str(exc)
        print(f"gh ошибка: {err}", file=sys.stderr)
        sys.exit(2)
    return json.loads(raw) if raw.strip() else None


def _repo_slug() -> str:
    """owner/name текущего remote origin."""
    url = subprocess.check_output(
        ["git", "remote", "get-url", "origin"],
        text=True,
    ).strip()
    # git@github.com:owner/repo.git | https://github.com/owner/repo.git
    path = url.rstrip("/").removesuffix(".git")
    if "github.com:" in path:
        path = path.split("github.com:", 1)[1]
    elif "github.com/" in path:
        path = path.split("github.com/", 1)[1]
    return path


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _job_minutes(started_at: str | None, completed_at: str | None) -> float:
    """Минуты одного job (округление вверх до целой минуты как у GitHub)."""
    start = _parse_iso(started_at)
    end = _parse_iso(completed_at)
    if start is None or end is None or end <= start:
        return 0.0
    seconds = (end - start).total_seconds()
    # GitHub округляет каждую job вверх до минуты.
    return float(math.ceil(seconds / 60.0))


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        return {
            "manual_used_minutes": None,
            "runs": {},
            "updated_at": None,
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _list_month_runs(repo: str, month_start: date) -> list[dict[str, Any]]:
    """Все завершённые runs репо с начала месяца (пагинация gh)."""
    created = f">={month_start.isoformat()}T00:00:00Z"
    runs: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = _gh_json(
            [
                "api",
                (
                    f"repos/{repo}/actions/runs"
                    f"?per_page=100&page={page}&created={created}"
                ),
                "--jq",
                ".workflow_runs",
            ],
        )
        if not batch:
            break
        assert isinstance(batch, list)
        runs.extend(batch)
        if len(batch) < 100:
            break
        page += 1
        if page > 20:
            break
    return runs


def _run_job_minutes(repo: str, run_id: int) -> tuple[float, list[dict[str, Any]]]:
    """Сумма billable-минут по job'ам одного run."""
    jobs = _gh_json(
        [
            "api",
            f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
            "--jq",
            ".jobs",
        ],
    )
    if not jobs:
        return 0.0, []
    assert isinstance(jobs, list)
    details: list[dict[str, Any]] = []
    total = 0.0
    for job in jobs:
        mins = _job_minutes(job.get("started_at"), job.get("completed_at"))
        total += mins
        details.append(
            {
                "name": job.get("name"),
                "conclusion": job.get("conclusion"),
                "minutes": mins,
            },
        )
    return total, details


def refresh_from_github(state: dict[str, Any], period: Period) -> dict[str, Any]:
    """Обновить кэш минут по runs текущего месяца."""
    repo = _repo_slug()
    runs = _list_month_runs(repo, period.month_start)
    cached: dict[str, Any] = state.setdefault("runs", {})
    # Сбросить runs вне текущего месяца (смена периода).
    month_prefix = f"{period.year}-{period.month:02d}"
    for key in list(cached):
        meta = cached[key]
        created = str(meta.get("created_at", ""))
        if not created.startswith(month_prefix):
            del cached[key]

    for run in runs:
        run_id = str(run["id"])
        created_at = run.get("created_at") or run.get("run_started_at") or ""
        status = run.get("status")
        if status != "completed":
            continue
        # Не пересчитывать неизменённый completed run.
        prev = cached.get(run_id)
        if (
            prev
            and prev.get("conclusion") == run.get("conclusion")
            and prev.get("updated_at") == run.get("updated_at")
        ):
            continue
        minutes, jobs = _run_job_minutes(repo, int(run_id))
        cached[run_id] = {
            "created_at": created_at,
            "updated_at": run.get("updated_at"),
            "conclusion": run.get("conclusion"),
            "title": run.get("display_title") or run.get("name"),
            "minutes": minutes,
            "jobs": jobs,
        }

    state["runs"] = cached
    state["updated_at"] = datetime.now(UTC).isoformat()
    state["repo"] = repo
    state["period"] = f"{period.year}-{period.month:02d}"
    return state


def _sum_minutes(
    runs: dict[str, Any],
    *,
    start: date,
    end: date,
) -> float:
    total = 0.0
    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC)
    for meta in runs.values():
        created = _parse_iso(meta.get("created_at"))
        if created is None:
            continue
        if start_dt <= created <= end_dt:
            total += float(meta.get("minutes") or 0)
    return total


def _bar(used: float, budget: float, width: int = 24) -> str:
    if budget <= 0:
        return "[" + "?" * width + "]"
    ratio = max(0.0, min(1.0, used / budget))
    filled = int(round(ratio * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def build_report(state: dict[str, Any], period: Period) -> dict[str, Any]:
    """Собрать отчёт: месяц / неделя / остатки."""
    runs = state.get("runs") or {}
    estimated_month = _sum_minutes(
        runs,
        start=period.month_start,
        end=period.month_end,
    )
    estimated_week = _sum_minutes(
        runs,
        start=period.week_start,
        end=period.week_end,
    )
    manual = state.get("manual_used_minutes")
    month_used = float(manual) if manual is not None else estimated_month
    # Если задан manual за месяц — неделю масштабируем долей оценки.
    if manual is not None and estimated_month > 0:
        week_used = month_used * (estimated_week / estimated_month)
    elif manual is not None:
        week_used = 0.0
    else:
        week_used = estimated_week

    month_left = max(0.0, MONTHLY_FREE_MINUTES - month_used)
    week_left = max(0.0, WEEKLY_BUDGET_MINUTES - week_used)
    # Равномерный «темп»: к концу недели N должно уйти ≤ N * 500.
    pace_cap = period.week * WEEKLY_BUDGET_MINUTES
    over_pace = month_used > pace_cap

    return {
        "monthly_budget": MONTHLY_FREE_MINUTES,
        "weekly_budget": WEEKLY_BUDGET_MINUTES,
        "weeks": WEEKS_PER_MONTH,
        "period": {
            "year": period.year,
            "month": period.month,
            "week": period.week,
            "week_start": period.week_start.isoformat(),
            "week_end": period.week_end.isoformat(),
            "month_start": period.month_start.isoformat(),
            "month_end": period.month_end.isoformat(),
        },
        "month_used": round(month_used, 1),
        "month_left": round(month_left, 1),
        "week_used": round(week_used, 1),
        "week_left": round(week_left, 1),
        "estimated_month": round(estimated_month, 1),
        "estimated_week": round(estimated_week, 1),
        "manual_used_minutes": manual,
        "source": "manual" if manual is not None else "estimate",
        "over_pace": over_pace,
        "pace_cap": pace_cap,
        "runs_counted": len(runs),
        "updated_at": state.get("updated_at"),
        "repo": state.get("repo"),
    }


def print_human(report: dict[str, Any]) -> None:
    """Человекочитаемый вывод счётчика."""
    p = report["period"]
    print("══════════════════════════════════════════════════")
    print("  GitHub Actions — минуты CI (public: биллинг не списывается)")
    print("══════════════════════════════════════════════════")
    print(
        f"  Репо:     {report.get('repo') or '—'}",
    )
    print(
        f"  Период:   {p['year']}-{p['month']:02d}"
        f"  · неделя {p['week']}/{WEEKS_PER_MONTH}"
        f"  ({p['week_start']} … {p['week_end']})",
    )
    print(
        f"  Источник: {report['source']}"
        + (
            f"  (оценка по runs: {report['estimated_month']} мин)"
            if report["source"] == "manual"
            else f"  ({report['runs_counted']} runs)"
        ),
    )
    if report.get("updated_at"):
        print(f"  Обновлено: {report['updated_at']}")
    print()
    print(
        f"  Месяц  {report['month_used']:7.1f} / {report['monthly_budget']} мин  "
        f"осталось {report['month_left']:.1f}  "
        f"{_bar(report['month_used'], report['monthly_budget'])}",
    )
    print(
        f"  Неделя {report['week_used']:7.1f} / {report['weekly_budget']} мин  "
        f"осталось {report['week_left']:.1f}  "
        f"{_bar(report['week_used'], report['weekly_budget'])}",
    )
    print()
    if report["over_pace"]:
        print(
            f"  ⚠ Темп выше плана: к неделе {p['week']} лимит равномерности"
            f" = {report['pace_cap']} мин, сейчас {report['month_used']:.1f}.",
        )
    else:
        print(
            f"  ✓ Темп в норме (к неделе {p['week']} ≤ {report['pace_cap']} мин).",
        )
    print()
    print("  Подсказка: сверка с UI → Settings → Billing → Actions usage")
    print("            ./scripts/actions-minutes.py --set-used N")
    print("            ./scripts/actions-minutes.py --refresh")
    print("══════════════════════════════════════════════════")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Статистика минут GitHub Actions "
            f"({MONTHLY_FREE_MINUTES}/мес → {WEEKLY_BUDGET_MINUTES}/нед × 4; "
            "public repo — без списания с биллинга)."
        ),
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Обновить оценку по workflow runs через gh API",
    )
    parser.add_argument(
        "--set-used",
        type=float,
        metavar="MINUTES",
        help="Задать факт из UI биллинга (минуты за текущий месяц)",
    )
    parser.add_argument(
        "--clear-manual",
        action="store_true",
        help="Сбросить ручное значение, снова только оценка",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести отчёт в JSON",
    )
    args = parser.parse_args()

    today = datetime.now(UTC).date()
    period = Period.for_day(today)
    state = _load_state()

    # Новый календарный месяц — сбросить manual и чужой кэш.
    if state.get("period") and state["period"] != f"{period.year}-{period.month:02d}":
        state["manual_used_minutes"] = None
        state["runs"] = {}

    if args.clear_manual:
        state["manual_used_minutes"] = None

    if args.set_used is not None:
        if args.set_used < 0:
            print("--set-used не может быть отрицательным", file=sys.stderr)
            return 2
        state["manual_used_minutes"] = float(args.set_used)
        state["period"] = f"{period.year}-{period.month:02d}"
        state["updated_at"] = datetime.now(UTC).isoformat()

    need_refresh = args.refresh or not state.get("runs") or not state.get("updated_at")
    if need_refresh:
        print("Обновляю оценку по GitHub Actions runs…", file=sys.stderr)
        state = refresh_from_github(state, period)

    _save_state(state)
    report = build_report(state, period)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
