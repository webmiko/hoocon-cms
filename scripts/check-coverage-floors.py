#!/usr/bin/env python3
"""Per-app coverage ratchet for the backend (run after ``pytest --cov``).

Usage (from ``backend/``)::

    poetry run python ../scripts/check-coverage-floors.py

Floors are the measured level (rounded down to 0.5) since ``admin.py`` and
``admin/*`` joined the measured code; raise a floor when tests improve an
app, never lower it to pass CI. Exit 1 when any app drops below its floor.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict

APP_FLOORS: dict[str, float] = {
    "accounts": 80.5,
    "analytics": 92.0,
    "cabinet": 82.5,
    "catalog": 91.0,
    "config": 90.5,
    "content": 86.0,
    "crm": 86.5,
    "leads": 82.0,
    "redirects": 91.0,
    "search": 96.0,
    "sitesettings": 89.5,
    "social": 64.5,
    "staff_api": 73.0,
    "supportchat": 80.0,
    "webpush": 72.5,
}


def _app_totals(report: dict) -> dict[str, list[int]]:
    """Sum covered/total lines+branches per top-level app."""
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for path, data in report["files"].items():
        app = path.split("/", 1)[0]
        summary = data["summary"]
        covered = summary["covered_lines"] + summary.get("covered_branches", 0)
        total = summary["num_statements"] + summary.get("num_branches", 0)
        totals[app][0] += covered
        totals[app][1] += total
    return totals


def main() -> int:
    raw = subprocess.run(
        ["coverage", "json", "-o", "-", "--fail-under=0", "-q"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    totals = _app_totals(json.loads(raw))
    failures: list[str] = []
    for app, floor in sorted(APP_FLOORS.items()):
        covered, total = totals.get(app, [0, 0])
        if total == 0:
            failures.append(f"{app}: not measured (add it to [tool.coverage.run] source)")
            continue
        pct = 100.0 * covered / total
        mark = "ok " if pct >= floor else "LOW"
        print(f"{mark} {app:<13} {pct:5.1f}% (floor {floor:.1f}%)")
        if pct < floor:
            failures.append(f"{app}: {pct:.1f}% < floor {floor:.1f}%")
    unmeasured = sorted(set(totals) - set(APP_FLOORS))
    if unmeasured:
        failures.append(f"apps without a floor: {', '.join(unmeasured)}")
    if failures:
        print("\n".join(["Coverage floors failed:", *failures]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
