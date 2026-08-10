"""CSV import helpers for Redirect seeds (typo slugs + Tilda /tproduct/)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from django.db import transaction

from redirects.models import Redirect
from redirects.pathutils import normalize_path, validate_internal_path

REQUIRED_COLUMNS = ("from_path", "to_path", "status_code")


def load_redirects_from_csv(path: Path, *, dry_run: bool = False) -> dict[str, int]:
    """Upsert Redirect rows from a CSV seed file.

    Args:
        path: CSV with columns from_path, to_path, status_code (optional note ignored).
        dry_run: If True, validate only and do not write.

    Returns:
        Counters: created, updated, skipped, total.

    Raises:
        ValueError: Missing columns or invalid row data.
        FileNotFoundError: CSV path does not exist.
    """
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")

    created = 0
    updated = 0
    skipped = 0
    total = 0

    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"Empty CSV: {path}")
        missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV {path} missing columns: {', '.join(missing)}")

        rows: list[dict[str, Any]] = []
        for row in reader:
            total += 1
            from_path = normalize_path(row["from_path"].strip())
            to_path = normalize_path(row["to_path"].strip())
            status_raw = (row.get("status_code") or "301").strip()
            try:
                status_code = int(status_raw)
            except ValueError as exc:
                raise ValueError(f"Invalid status_code in {path}: {status_raw!r}") from exc
            if status_code not in (
                Redirect.HTTP_MOVED_PERMANENTLY,
                Redirect.HTTP_FOUND,
            ):
                raise ValueError(f"Unsupported status_code {status_code} in {path}")
            validate_internal_path(from_path)
            validate_internal_path(to_path)
            if from_path == to_path:
                raise ValueError(f"Self-redirect in {path}: {from_path}")
            rows.append(
                {
                    "from_path": from_path,
                    "to_path": to_path,
                    "status_code": status_code,
                }
            )

    if dry_run:
        return {"created": 0, "updated": 0, "skipped": total, "total": total}

    with transaction.atomic():
        for item in rows:
            _obj, was_created = Redirect.objects.update_or_create(
                from_path=item["from_path"],
                defaults={
                    "to_path": item["to_path"],
                    "status_code": item["status_code"],
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return {"created": created, "updated": updated, "skipped": skipped, "total": total}


def render_nginx_map(redirects: list[Redirect]) -> str:
    """Render an nginx map body for active redirects.

    Args:
        redirects: Active Redirect rows.

    Returns:
        Text suitable for ``deploy/nginx/redirects.map``.
    """
    lines = [
        "# Generated from Redirect seeds — typo slugs + Tilda /tproduct/.",
        "# Format: $uri $redirect_uri;",
        "",
    ]
    for item in redirects:
        lines.append(f"{item.from_path} {item.to_path};")
    lines.append("")
    return "\n".join(lines)
