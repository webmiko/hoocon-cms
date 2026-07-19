"""Quarantine CSV writer for ETL bad rows.

Spec: docs/data-quality-etl.md §4 — падающий ряд → quarantine CSV, не в prod.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def write_quarantine_csv(
    rows: list[dict[str, Any]],
    output_path: Path,
) -> int:
    """Write quarantined rows to a CSV file.

    Args:
        rows: list of dicts with at least 'reason' and 'payload' keys.
        output_path: destination CSV file.

    Returns:
        Number of rows written.
    """
    if not rows:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["reason", "uid", "title", "detail"]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = row.get("payload") or {}
            writer.writerow(
                {
                    "reason": row.get("reason", ""),
                    "uid": payload.get("uid", ""),
                    "title": payload.get("title", ""),
                    "detail": str(payload)[:500],
                },
            )
    return len(rows)
