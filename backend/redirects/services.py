"""CSV import helpers for Redirect seeds (typo slugs + Tilda /tproduct/)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from django.db import transaction

from redirects.models import Redirect
from redirects.pathutils import is_safe_internal_path, normalize_path, validate_internal_path

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
        locked = set(
            Redirect.objects.filter(
                from_path__in=[item["from_path"] for item in rows],
                edited_in_admin=True,
            ).values_list("from_path", flat=True)
        )
        for item in rows:
            if item["from_path"] in locked:
                skipped += 1
                continue
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

    from redirects.lookup import clear_redirect_index

    clear_redirect_index()
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
        # Unquoted map syntax: an unsafe path would break or inject config.
        if is_safe_internal_path(item.from_path) and is_safe_internal_path(item.to_path):
            lines.append(f"{item.from_path} {item.to_path};")
    lines.append("")
    return "\n".join(lines)


_MAX_CHAIN_HOPS = 10


def collapse_redirect_chains(*, dry_run: bool = False) -> int:
    """Point ``A → B → C`` straight at ``C`` (one 301 hop for crawlers).

    Rows edited in Admin are left as they are; cycles are skipped.

    Returns:
        Number of rows rewritten (or that would be in ``dry_run``).
    """
    active = dict(Redirect.objects.filter(is_active=True).values_list("from_path", "to_path"))
    rewritten = 0
    for row in Redirect.objects.filter(is_active=True, edited_in_admin=False).iterator():
        final = row.to_path
        seen = {row.from_path}
        hops = 0
        while final in active and final not in seen and hops < _MAX_CHAIN_HOPS:
            seen.add(final)
            final = active[final]
            hops += 1
        if final in seen or final == row.to_path or final == row.from_path:
            continue
        rewritten += 1
        if not dry_run:
            Redirect.objects.filter(pk=row.pk).update(to_path=final)
            active[row.from_path] = final
    return rewritten
