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


@pytest.mark.django_db
def test_public_lead_rejects_call_stub_email(client) -> None:
    """Форма сайта с @call.invalid не становится карточкой «Звонок пропущен»."""
    from crm.models import Client

    response = client.post(
        "/api/leads/",
        data={
            "pdn_consent": True,
            "name": "Бот",
            "email": "79991234567@call.invalid",
            "company": "Пустышка",
            "message": "Это не звонок, это форма.",
        },
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not Client.objects.filter(email__iendswith="@call.invalid").exists()


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
