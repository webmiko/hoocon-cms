"""Apply an upload package of reference ProductImage files to a database.

The package (``manifest.json`` + ``files/``) describes three row actions:

- ``replace``: refresh bytes/alt/sort of an existing row keyed by
  ``(sku, source_url)`` — the prediction must be ``update``; a ``create``
  prediction means the key is absent and applying would duplicate the gallery;
- ``add``: insert a row that does not exist yet — prediction ``create``;
- ``unpublish``: hide a legacy row (e.g. marketplace-scrape combined schemes
  superseded by manual-derived wiring/dimensions rows).

Safety rails:

- dry-run gate: predictions are computed through the real
  :func:`upsert_sku_image` path; fatal anomalies (missing SKU, locked row,
  replace-would-create, add-would-update, unexpected skip) block ``--yes``;
- before the first write a rollback snapshot records the full row state and
  a byte copy of every image/image_card about to be replaced or unpublished,
  so the pre-upload state can be restored even though upsert writes new files.
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from PIL import Image

from catalog.etl.image_upsert import upsert_sku_image
from catalog.models import SKU, ProductImage

MAX_PACKAGE_FILE_BYTES = 8 * 1024 * 1024


@dataclass
class PlanRow:
    """One manifest entry with its predicted application result."""

    group_action: str
    sku_code: str
    source_url: str
    entry: dict[str, Any]
    package_file: Path | None = None
    webp: bytes = b""
    sku: SKU | None = None
    row: ProductImage | None = None
    prediction: str = ""
    fatal: str = ""
    skip: bool = False


@dataclass
class Package:
    """Validated upload package: manifest payload plus verified file bytes."""

    package_dir: Path
    manifest: dict[str, Any]
    group_bytes: dict[int, bytes] = field(default_factory=dict)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_package(package_dir: Path) -> Package:
    """Read manifest.json and verify every referenced package file by sha256.

    Raises:
        ValueError: manifest missing/invalid or a file hash mismatches — the
            package must be rejected before any database work.
    """
    manifest_path = package_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"manifest.json not found in {package_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    groups = manifest.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("manifest has no groups")
    package_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    package = Package(package_dir=package_dir, manifest=manifest)
    problems: list[str] = []
    for index, group in enumerate(groups):
        action = group.get("action")
        if action not in ("replace", "add", "unpublish"):
            problems.append(f"group {index}: unknown action {action!r}")
            continue
        problems.extend(_validate_entries(index, group))
        if action == "unpublish":
            continue
        rel = str(group.get("package_file") or "")
        rel_path = Path(rel)
        if not rel or rel_path.is_absolute() or ".." in rel_path.parts:
            problems.append(f"group {index}: package file escapes the package: {rel!r}")
            continue
        file_path = package_dir / rel
        if not file_path.is_file():
            problems.append(f"group {index}: package file missing: {rel!r}")
            continue
        actual = _file_sha256(file_path)
        if actual != (group.get("sha256") or ""):
            problems.append(f"group {index}: sha256 mismatch for {rel}")
            continue
        payload = file_path.read_bytes()
        if not _webp_decodable(payload):
            problems.append(f"group {index}: bytes do not decode as WebP: {rel}")
            continue
        package.group_bytes[index] = payload
    if problems:
        raise ValueError("; ".join(problems))
    package.manifest_sha256 = package_hash
    return package


def _validate_entries(index: int, group: dict[str, Any]) -> list[str]:
    """Catch entry defects that would otherwise crash full_clean mid-apply."""
    problems: list[str] = []
    for entry in group.get("entries") or []:
        sku = entry.get("sku_code") or "?"
        if group.get("action") == "unpublish":
            continue
        sort_order = entry.get("sort_order")
        if not isinstance(sort_order, int) or isinstance(sort_order, bool) or sort_order < 0:
            problems.append(f"group {index} {sku}: invalid sort_order {sort_order!r}")
        if not str(entry.get("alt") or "").strip():
            problems.append(f"group {index} {sku}: empty alt")
        if not str(entry.get("target_filename") or "").strip():
            problems.append(f"group {index} {sku}: empty target_filename")
    return problems


def _webp_decodable(payload: bytes) -> bool:
    """True when bytes fully decode as WebP — truncated payloads pass magic but
    would be published without a card preview (decode errors are swallowed)."""
    if len(payload) > MAX_PACKAGE_FILE_BYTES:
        return False
    try:
        with Image.open(io.BytesIO(payload)) as img:
            if img.format != "WEBP":
                return False
            img.load()
    except (OSError, ValueError):
        return False
    return True


def build_plan(package: Package) -> list[PlanRow]:
    """Resolve every manifest entry against the database and predict actions.

    Upsert predictions reuse :func:`upsert_sku_image` in dry-run mode, so the
    gate judges exactly the logic that would later write.
    """
    plan: list[PlanRow] = []
    groups = package.manifest["groups"]
    for index, group in enumerate(groups):
        action = group["action"]
        webp = package.group_bytes.get(index, b"")
        file_path = package.package_dir / (group.get("package_file") or "") if action != "unpublish" else None
        for entry in group.get("entries") or []:
            plan_row = PlanRow(
                group_action=action,
                sku_code=str(entry.get("sku_code") or ""),
                source_url=str(entry.get("source_url") or ""),
                entry=entry,
                package_file=file_path,
                webp=webp,
            )
            _resolve_plan_row(plan_row, webp)
            plan.append(plan_row)
    return plan


def _resolve_plan_row(plan_row: PlanRow, webp: bytes) -> None:
    sku = SKU.objects.filter(sku_code__iexact=plan_row.sku_code).first()
    if sku is None:
        plan_row.fatal = "missing-sku"
        return
    plan_row.sku = sku

    if plan_row.group_action == "unpublish":
        row = ProductImage.objects.filter(sku=sku, source_url=plan_row.source_url).first()
        if row is None:
            plan_row.fatal = "missing-row"
            return
        plan_row.row = row
        if row.image_locked:
            plan_row.fatal = "locked-row"
            return
        if not row.is_published:
            plan_row.prediction = "skip"
            plan_row.skip = True
        else:
            plan_row.prediction = "unpublish"
        return

    action, row = upsert_sku_image(
        sku,
        source_url=plan_row.source_url,
        filename=str(plan_row.entry.get("target_filename") or "image.webp"),
        webp=webp,
        alt=str(plan_row.entry.get("alt") or ""),
        sort_order=int(plan_row.entry.get("sort_order") or 0),
        dry_run=True,
    )
    plan_row.row = row
    plan_row.prediction = action
    if row is not None and row.image_locked:
        plan_row.fatal = "locked-row"
    elif plan_row.group_action == "replace" and action == "create":
        plan_row.fatal = "replace-would-create"
    elif plan_row.group_action == "add" and action == "update":
        plan_row.fatal = "add-would-update"
    elif action == "skip":
        plan_row.skip = True


def evaluate_gate(plan: list[PlanRow], *, allow_skip: bool) -> list[str]:
    """Return human-readable fatal anomalies; empty list means the gate passes."""
    anomalies: list[str] = []
    for plan_row in plan:
        label = f"{plan_row.sku_code} {plan_row.source_url}"
        if plan_row.fatal:
            anomalies.append(f"{plan_row.fatal}: {label}")
        elif plan_row.skip and not allow_skip:
            anomalies.append(f"unexpected-skip: {label}")
    return anomalies


def write_rollback_snapshot(plan: list[PlanRow], *, rollback_root: Path, package_dir: Path) -> Path:
    """Snapshot pre-write row state and byte copies before the first mutation.

    Returns:
        Path of the timestamped rollback directory with ``snapshot.json`` and
        ``files/`` copies; restoring means pointing rows back at these bytes.
    """
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    base = rollback_root / f"upload-rollback-{stamp}"
    target = base
    counter = 2
    while target.exists():
        target = base.with_name(f"{base.name}-{counter}")
        counter += 1
    files_dir = target / "files"
    files_dir.mkdir(parents=True)

    rows: list[dict[str, Any]] = []
    for plan_row in plan:
        if plan_row.group_action in ("replace", "add") and plan_row.prediction == "create":
            rows.append(
                {
                    "change": "create",
                    "sku_code": plan_row.sku_code,
                    "source_url": plan_row.source_url,
                    "note": "row did not exist before upload; rollback deletes it",
                },
            )
            continue
        row = plan_row.row
        if row is None:
            continue
        record: dict[str, Any] = {
            "change": "unpublish" if plan_row.group_action == "unpublish" else plan_row.prediction,
            "row_id": row.pk,
            "sku_code": plan_row.sku_code,
            "source_url": plan_row.source_url,
            "image": row.image.name or "",
            "image_card": row.image_card.name or "",
            "alt": row.alt,
            "sort_order": row.sort_order,
            "is_published": row.is_published,
            "was_published": row.is_published,
            "hidden_by_editor": row.hidden_by_editor,
            "sha256": "",
            "file_backup": "",
        }
        if plan_row.group_action != "unpublish" and row.image and row.image.name:
            try:
                with row.image.open("rb") as handle:
                    payload = handle.read()
            except OSError:
                # Файл уже потерян из storage — бэкапить нечего, upload и есть починка.
                record["sha256"] = ""
                payload = b""
            else:
                record["sha256"] = hashlib.sha256(payload).hexdigest()
            if payload:
                backup_name = f"files/{row.pk}_{Path(row.image.name).name}"
                backup_path = target / backup_name
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                backup_path.write_bytes(payload)
                record["file_backup"] = backup_name
            if row.image_card and row.image_card.name:
                try:
                    with row.image_card.open("rb") as handle:
                        card_payload = handle.read()
                    card_name = f"files/{row.pk}_card_{Path(row.image_card.name).name}"
                    (target / card_name).write_bytes(card_payload)
                    record["image_card_backup"] = card_name
                except OSError:
                    record["image_card_backup"] = ""
        rows.append(record)

    snapshot = {
        "created_at": stamp,
        "package_dir": str(package_dir),
        "rows": rows,
    }
    (target / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def upload_package(
    package_dir: Path,
    *,
    dry_run: bool,
    allow_skip: bool = False,
    rollback_root: Path | None = None,
    expect_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Plan, gate and optionally apply an upload package.

    Raises:
        ValueError: invalid package, or fatal gate anomalies in apply mode —
            raised before anything is written.
    """
    package = load_package(package_dir)
    plan = build_plan(package)
    anomalies = evaluate_gate(plan, allow_skip=allow_skip)

    counts = {"update": 0, "create": 0, "skip": 0, "unpublish": 0}
    for plan_row in plan:
        if plan_row.fatal:
            continue
        if plan_row.group_action == "unpublish" and plan_row.prediction != "skip":
            key = "unpublish"
        else:
            key = plan_row.prediction
        if key in counts:
            counts[key] += 1

    result: dict[str, Any] = {
        "manifest_sha256": package.manifest_sha256,
        "dry_run": dry_run,
        "plan": plan,
        "counts": counts,
        "anomalies": anomalies,
        "rollback_dir": None,
    }
    if dry_run:
        return result
    if anomalies:
        raise ValueError(f"gate refused apply: {'; '.join(anomalies[:5])}")
    if expect_counts:
        mismatched = {
            key: (counts.get(key, 0), want) for key, want in expect_counts.items() if counts.get(key, 0) != want
        }
        if mismatched:
            details = "; ".join(f"{key}: planned {got}, expected {want}" for key, (got, want) in mismatched.items())
            raise ValueError(f"expect-counts mismatch: {details}")

    root = rollback_root or (Path(settings.PRIVATE_MEDIA_ROOT) / "upload-rollback")
    result["rollback_dir"] = write_rollback_snapshot(plan, rollback_root=root, package_dir=package_dir)

    now = timezone.now()
    applied = {"update": 0, "create": 0, "skip": 0, "unpublish": 0}

    for plan_row in plan:
        if plan_row.group_action == "unpublish":
            if plan_row.prediction == "unpublish" and plan_row.row is not None:
                # hidden_by_editor — единственный durable unpublish: голое is_published=False
                # репаблишится ETL-джобами и upsert'ом.
                ProductImage.objects.filter(pk=plan_row.row.pk, is_published=True).update(
                    is_published=False,
                    hidden_by_editor=True,
                    updated_at=now,
                )
                applied["unpublish"] += 1
            else:
                applied["skip"] += 1
            continue

        action, _row = upsert_sku_image(
            plan_row.sku,
            source_url=plan_row.source_url,
            filename=str(plan_row.entry.get("target_filename") or "image.webp"),
            webp=plan_row.webp,
            alt=str(plan_row.entry.get("alt") or ""),
            sort_order=int(plan_row.entry.get("sort_order") or 0),
            dry_run=False,
        )
        applied[action] += 1

    result["applied"] = applied
    return result
