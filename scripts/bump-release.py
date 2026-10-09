#!/usr/bin/env python3
"""Bump the release version and sync every file that carries it.

Usage (repo root)::

    python3 scripts/bump-release.py patch   # feature on develop: 3.2.0 → 3.2.1 (UI v3.2)
    python3 scripts/bump-release.py minor   # prod release: 3.2.4 → 3.3.0 (UI v3.3)
    python3 scripts/bump-release.py major   # only on explicit command: → 4.0.0
    python3 scripts/bump-release.py --check # files agree with release.py

``--dry-run`` prints the plan without writing. Changelog line in
``_docs/releases.md`` stays manual.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PY = ROOT / "backend" / "config" / "release.py"

# (path, pattern with one capture group for the value, needs SemVer X.Y.Z)
TARGETS: tuple[tuple[Path, str, bool], ...] = (
    (RELEASE_PY, r'^RELEASE_VERSION = "([^"]+)"$', False),
    (ROOT / "frontend" / "src" / "release.ts", r'^export const RELEASE_VERSION = "([^"]+)";$', False),
    (ROOT / "backend" / "pyproject.toml", r'^version = "([^"]+)"$', True),
    (ROOT / "frontend" / "package.json", r'^  "version": "([^"]+)",$', True),
)


def _load_release() -> ModuleType:
    """Load release.py by path: ``config/__init__`` pulls in Celery."""
    spec = importlib.util.spec_from_file_location("hoocon_release", RELEASE_PY)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load {RELEASE_PY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _current(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), flags=re.MULTILINE)
    if match is None:
        raise SystemExit(f"Version line not found in {path.relative_to(ROOT)}")
    return match.group(1)


def _write(path: Path, pattern: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if match is None:
        raise SystemExit(f"Version line not found in {path.relative_to(ROOT)}")
    start, end = match.span(1)
    path.write_text(text[:start] + value + text[end:], encoding="utf-8")


def check(release: ModuleType) -> int:
    """Exit code 0 when every target matches ``RELEASE_VERSION``."""
    canon = release.RELEASE_VERSION
    semver = release.package_version(canon)
    bad = 0
    for path, pattern, needs_semver in TARGETS:
        want = semver if needs_semver else canon
        got = _current(path, pattern)
        if got != want:
            print(f"{path.relative_to(ROOT)}: {got} != {want}", file=sys.stderr)
            bad += 1
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("part", nargs="?", choices=("patch", "minor", "major"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    release = _load_release()
    if args.check:
        return check(release)
    if args.part is None:
        parser.error("part is required (patch | minor | major) unless --check")
    if release.RELEASE_CHANNEL:
        raise SystemExit("Pre-release channel set; bump beta versions by hand.")

    old = release.RELEASE_VERSION
    new = release.bump_version(old, args.part)
    old_label = f"v{release.display_version(old, channel='')}"
    new_label = f"v{release.display_version(new, channel='')}"
    note = "prod label changes" if old_label != new_label else "internal, prod label unchanged"
    print(f"{old} → {new}  ({old_label} → {new_label}; {note})")
    if args.dry_run:
        return 0

    semver = release.package_version(new)
    for path, pattern, needs_semver in TARGETS:
        _write(path, pattern, semver if needs_semver else new)
    return check(_load_release())


if __name__ == "__main__":
    raise SystemExit(main())
