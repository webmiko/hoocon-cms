"""Regressions for the confirmed items in the 2026-10 review."""

from __future__ import annotations

import os
import subprocess
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.utils import timezone

ROOT = Path(__file__).resolve().parents[2]


def test_backup_prune_keeps_newest_complete_copies(tmp_path: Path) -> None:
    """Уборка не стирает последние полные копии и не трогает незавершённый свежий каталог."""
    root = tmp_path / "backups"
    root.mkdir()

    def _dir(name: str, *, complete: bool, age_days: float) -> Path:
        path = root / name
        path.mkdir()
        if complete:
            (path / "COMPLETED").write_text(name, encoding="utf-8")
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    keep_a = _dir("a", complete=True, age_days=10)
    keep_b = _dir("b", complete=True, age_days=20)
    keep_c = _dir("c", complete=True, age_days=30)
    drop_old = _dir("d", complete=True, age_days=40)
    drop_partial = _dir("partial-old", complete=False, age_days=40)
    fresh = _dir("partial-new", complete=False, age_days=0)
    script = ROOT / "scripts" / "backup-retention.sh"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{script}"; hoocon_prune_backups "{root}" 7 3',
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert keep_a.is_dir() and keep_b.is_dir() and keep_c.is_dir()
    assert not drop_old.exists()
    assert not drop_partial.exists()
    assert fresh.is_dir()
