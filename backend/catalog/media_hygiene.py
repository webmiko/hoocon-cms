"""Dead media hygiene: find files on disk not referenced by any DB field.

Django does not delete storage files when rows are deleted or re-uploaded,
so ETL iterations accumulate orphans under ``MEDIA_ROOT``. This module
collects every path referenced by FileField/ImageField values and by
``/media/…`` URLs embedded in text/JSON columns, then diffs that set
against the on-disk tree.

Dead files are moved to ``MEDIA_ROOT/_quarantine/<stamp>/`` (never deleted
in place); a separate purge step removes a quarantine batch for good.
"""

from __future__ import annotations

import functools
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist, SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_save

MEDIA_URL_RE = re.compile(r"/media/([^\s\"'<>)\\]+)")
# Never treated as live content: ``_pack`` is ETL staging (opt-in via
# include_pack), ``_quarantine`` holds pruned batches.
PACK_DIRNAME = "_pack"
QUARANTINE_DIRNAME = "_quarantine"
MANIFEST_NAME = "manifest.txt"


def collect_referenced_media_paths() -> set[str]:
    """Return every media-relative path referenced from the database.

    Covers FileField/ImageField values plus ``/media/…`` URLs embedded in
    TextField/CharField/JSONField content (article bodies, JSON payloads).
    """
    referenced: set[str] = set()
    for model in apps.get_models():
        file_fields = [f for f in model._meta.fields if isinstance(f, models.FileField)]
        text_fields = [
            f.name
            for f in model._meta.fields
            if isinstance(f, (models.TextField, models.CharField, models.JSONField))
            and not isinstance(f, models.FileField)
        ]
        if not file_fields and not text_fields:
            continue
        for row in model._default_manager.all().iterator(chunk_size=2000):
            for field in file_fields:
                value = getattr(row, field.attname)
                if value:
                    referenced.add(str(value))
            for name in text_fields:
                value = getattr(row, name)
                if not value:
                    continue
                text = value if isinstance(value, str) else str(value)
                referenced.update(MEDIA_URL_RE.findall(text))
    return referenced


def collect_fixture_media_refs(repo_root: Path) -> set[str]:
    """Return ``/media/…`` paths referenced by repo fixture files.

    Fixtures are re-import sources: if a row is deleted but its fixture
    stays, the referenced files must not be pruned — a re-import would
    render broken media otherwise.
    """
    refs: set[str] = set()
    for path in repo_root.glob("*/fixtures/**/*"):
        if not path.is_file():
            continue
        try:
            refs.update(MEDIA_URL_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return refs


def scan_media_tree(root: Path, *, include_pack: bool = False) -> dict[str, int]:
    """Map media-relative path → size for regular files under ``root``.

    ``_quarantine`` is always skipped; ``_pack`` is skipped unless
    ``include_pack`` (it is ETL staging, not DB-referenced by design).
    """
    skip = {QUARANTINE_DIRNAME} if include_pack else {QUARANTINE_DIRNAME, PACK_DIRNAME}
    files: dict[str, int] = {}
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.split("/", 1)[0] in skip:
            continue
        files[rel] = path.stat().st_size
    return files


def audit_dead_media(
    root: Path,
    *,
    include_pack: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Diff disk tree vs DB + fixture references; return dead and missing sets."""
    referenced = collect_referenced_media_paths()
    if repo_root is not None:
        referenced |= collect_fixture_media_refs(repo_root)
    on_disk = scan_media_tree(root, include_pack=include_pack)
    dead = set(on_disk) - referenced
    missing = referenced - set(on_disk)
    return {
        "referenced": len(referenced),
        "on_disk": on_disk,
        "dead": dead,
        "missing": missing,
    }


def bucket_stats(paths: set[str], on_disk: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Group paths by top-level dir → (count, bytes)."""
    agg: dict[str, tuple[int, int]] = {}
    for rel in paths:
        top = rel.split("/", 1)[0]
        count, size = agg.get(top, (0, 0))
        agg[top] = (count + 1, size + on_disk.get(rel, 0))
    return agg


def quarantine_dead_media(root: Path, dead: set[str], on_disk: dict[str, int]) -> Path:
    """Move dead files into ``root/_quarantine/<utc-stamp>/`` with a manifest.

    Returns the quarantine batch directory.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    batch_dir = root / QUARANTINE_DIRNAME / stamp
    moved: list[str] = []
    for rel in sorted(dead):
        src = root / rel
        if not src.is_file():
            continue
        dst = batch_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(rel)
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest = batch_dir / MANIFEST_NAME
    manifest.write_text("\n".join(moved) + ("\n" if moved else ""), encoding="utf-8")
    _prune_empty_dirs(root, skip={QUARANTINE_DIRNAME})
    return batch_dir


def purge_quarantine_batch(root: Path, batch_name: str) -> int:
    """Delete one quarantine batch dir; return number of files removed.

    ``batch_name`` must be a single directory name inside ``_quarantine``.
    """
    if not batch_name or batch_name in (".", "..") or "/" in batch_name or "\\" in batch_name:
        msg = f"Unsafe quarantine batch name: {batch_name!r}"
        raise ValueError(msg)
    batch_dir = root / QUARANTINE_DIRNAME / batch_name
    if not batch_dir.is_dir():
        msg = f"Quarantine batch not found: {batch_dir}"
        raise FileNotFoundError(msg)
    count = sum(1 for p in batch_dir.rglob("*") if p.is_file())
    shutil.rmtree(batch_dir)
    return count


def list_quarantine_batches(root: Path) -> list[str]:
    """Return quarantine batch directory names, oldest first."""
    quarantine = root / QUARANTINE_DIRNAME
    if not quarantine.is_dir():
        return []
    return sorted(d.name for d in quarantine.iterdir() if d.is_dir())


def _prune_empty_dirs(root: Path, *, skip: set[str]) -> None:
    """Remove empty directories left after moves (bottom-up)."""
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_dir():
            continue
        rel_top = path.relative_to(root).parts[0]
        if rel_top in skip:
            continue
        try:
            path.rmdir()
        except OSError:
            continue


def _file_fields(model: type[models.Model]) -> list[models.FileField]:
    """All FileField/ImageField declared on ``model``."""
    return [f for f in model._meta.fields if isinstance(f, models.FileField)]


def _prune_empty_parents(storage: Any, file_name: str) -> None:
    """Rmdir now-empty parent dirs of a deleted file (filesystem storages)."""
    if not isinstance(storage, FileSystemStorage):
        return
    try:
        root = Path(storage.location).resolve()
        parent = Path(storage.path(file_name)).resolve().parent
    except (OSError, SuspiciousFileOperation):
        return
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            return
        parent = parent.parent


def _delete_field_file(
    model: type[models.Model],
    field_name: str,
    file_name: str,
    *,
    exclude_pk: Any = None,
) -> bool:
    """Delete ``file_name`` unless another row of ``model`` still references it."""
    if not file_name:
        return False
    shared = model._default_manager.filter(**{field_name: file_name})
    if exclude_pk is not None:
        shared = shared.exclude(pk=exclude_pk)
    if shared.exists():
        return False
    field = model._meta.get_field(field_name)
    if not isinstance(field, models.FileField):
        return False
    if not field.storage.exists(file_name):
        return False
    field.storage.delete(file_name)
    _prune_empty_parents(field.storage, file_name)
    return True


def cleanup_media_on_delete(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    """post_delete: remove field files of the deleted row (unshared only)."""
    for field in _file_fields(sender):
        _delete_field_file(sender, field.name, str(getattr(instance, field.attname) or ""))


def cleanup_media_on_save(sender: type[models.Model], instance: models.Model, **kwargs: Any) -> None:
    """pre_save: after commit, drop files replaced by a new upload on the row."""
    if instance.pk is None or instance._state.adding:
        return
    fields = _file_fields(sender)
    try:
        old = sender._default_manager.only(*(f.name for f in fields)).get(pk=instance.pk)
    except ObjectDoesNotExist:
        return
    for field in fields:
        old_name = str(getattr(old, field.attname) or "")
        new_name = str(getattr(instance, field.attname) or "")
        if old_name and old_name != new_name:
            transaction.on_commit(
                functools.partial(
                    _delete_field_file,
                    sender,
                    field.name,
                    old_name,
                    exclude_pk=instance.pk,
                ),
            )


def register_file_cleanup(*models_: type[models.Model]) -> None:
    """Wire file cleanup signals for models with FileField/ImageField.

    Called from ``apps.py ready()`` so every row delete or file replace
    frees storage instead of leaving an orphan.
    """
    for model in models_:
        label = model._meta.label_lower
        post_delete.connect(
            cleanup_media_on_delete,
            sender=model,
            dispatch_uid=f"media_hygiene.delete.{label}",
        )
        pre_save.connect(
            cleanup_media_on_save,
            sender=model,
            dispatch_uid=f"media_hygiene.save.{label}",
        )
