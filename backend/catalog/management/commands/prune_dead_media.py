"""Quarantine media files on disk that no DB row or content references.

Usage::

    poetry run python manage.py prune_dead_media                 # dry-run report
    poetry run python manage.py prune_dead_media --apply         # move dead → _quarantine/<stamp>/
    poetry run python manage.py prune_dead_media --purge <stamp> --yes   # delete batch for good
    poetry run python manage.py prune_dead_media --list-quarantine
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.media_hygiene import (
    audit_dead_media,
    bucket_stats,
    list_quarantine_batches,
    purge_quarantine_batch,
    quarantine_dead_media,
)


class Command(BaseCommand):
    """Report, quarantine, or purge orphaned files under MEDIA_ROOT."""

    help = "Move media files unreferenced by any DB field into _quarantine/ (dry-run by default)."

    def add_arguments(self, parser: Any) -> None:
        """Register mode flags."""
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Move dead files to MEDIA_ROOT/_quarantine/<utc-stamp>/ (default: dry-run report).",
        )
        parser.add_argument(
            "--purge",
            metavar="BATCH",
            help="Permanently delete a quarantine batch dir (requires --yes).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm --purge without an interactive prompt.",
        )
        parser.add_argument(
            "--include-pack",
            action="store_true",
            help="Also scan _pack/ ETL staging (never DB-referenced by design).",
        )
        parser.add_argument(
            "--list-quarantine",
            action="store_true",
            help="List quarantine batches and exit.",
        )
        parser.add_argument(
            "--media-root",
            help="Override MEDIA_ROOT (default: settings.MEDIA_ROOT).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Dispatch to purge / list / audit+quarantine."""
        root = Path(options.get("media_root") or settings.MEDIA_ROOT)
        if options.get("list_quarantine"):
            batches = list_quarantine_batches(root)
            self.stdout.write("quarantine batches: " + (", ".join(batches) if batches else "none"))
            return
        purge_batch = options.get("purge")
        if purge_batch:
            self._purge(root, purge_batch, yes=bool(options.get("yes")))
            return
        self._audit_and_maybe_quarantine(root, options)

    def _purge(self, root: Path, batch_name: str, *, yes: bool) -> None:
        """Delete a quarantine batch after confirmation."""
        if not yes:
            confirm = input(f"Delete quarantine batch {batch_name!r} permanently? [y/N] ")
            if confirm.strip().lower() not in ("y", "yes"):
                self.stdout.write("aborted")
                return
        try:
            removed = purge_quarantine_batch(root, batch_name)
        except (ValueError, FileNotFoundError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"purged {batch_name}: {removed} files")

    def _audit_and_maybe_quarantine(self, root: Path, options: dict[str, Any]) -> None:
        """Report dead files; move them to quarantine when --apply."""
        include_pack = bool(options.get("include_pack"))
        repo_root = Path(settings.BASE_DIR)
        report = audit_dead_media(root, include_pack=include_pack, repo_root=repo_root)
        on_disk = report["on_disk"]
        dead = report["dead"]
        missing = report["missing"]

        self.stdout.write(f"media root: {root}")
        self.stdout.write(f"referenced by DB/content: {report['referenced']} paths")
        self.stdout.write(f"on disk (scanned): {len(on_disk)} files")
        self._write_stats("dead (no reference)", dead, on_disk)
        if missing:
            self.stdout.write(f"missing (DB references, no file): {len(missing)}")
            for rel in sorted(missing)[:20]:
                self.stdout.write(f"  {rel}")

        if not dead:
            return
        if not options.get("apply"):
            self.stdout.write("dry-run: pass --apply to move dead files to _quarantine/")
            return
        batch_dir = quarantine_dead_media(root, dead, on_disk)
        self.stdout.write(f"quarantined {len(dead)} files → {batch_dir}")

    def _write_stats(self, label: str, paths: set[str], on_disk: dict[str, int]) -> None:
        """Print per-top-dir counts and sizes."""
        total = sum(on_disk.get(rel, 0) for rel in paths)
        self.stdout.write(f"{label}: {len(paths)} files, {total / 2**30:.2f} GiB")
        for top, (count, size) in sorted(bucket_stats(paths, on_disk).items(), key=lambda item: -item[1][1]):
            self.stdout.write(f"  {count:>8} {size / 2**30:>7.2f} GiB  {top}")
