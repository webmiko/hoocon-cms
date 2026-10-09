"""scripts/sync-manual-pdfs.sh: локальные PDF мануалов → прод без ручных шагов.

Скрипт гоняется с заглушками ssh/rsync в PATH: проверяем, что он заливает
только при изменениях, не снимает PDF с сайта и не помечает неудачный
прогон как успешный.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync-manual-pdfs.sh"

_SSH_STUB = """#!/usr/bin/env bash
echo "ssh $*" >> "$CALLS"
if [[ "$*" == *"bash -s"* ]]; then
  cat >> "$CALLS"
  echo "DAMU manuals=1 created=1 updated=2 skipped=5"
  echo "PASSPORT manuals=8 created=0 updated=0 skipped=8"
fi
"""

_RSYNC_STUB = """#!/usr/bin/env bash
echo "rsync $*" >> "$CALLS"
exit "${RSYNC_EXIT:-0}"
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _setup(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "ssh", _SSH_STUB)
    _write_exec(bin_dir / "rsync", _RSYNC_STUB)
    manuals = tmp_path / "manuals"
    for sub in ("RU", "EN", "паспорт изделия"):
        (manuals / sub).mkdir(parents=True)
    pdf = manuals / "паспорт изделия" / "DA8MU24-A — паспорт (RU).pdf"
    pdf.write_bytes(b"%PDF-v1")
    old = time.time() - 3600
    os.utime(pdf, (old, old))
    calls = tmp_path / "calls.log"
    # pytest-cov env makes the script's inline python3 write statement-only data
    # that cannot be combined with the branch run («Can't combine … branch data»).
    inherited = {k: v for k, v in os.environ.items() if not k.startswith(("COV_CORE_", "COVERAGE_"))}
    env = {
        **inherited,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS": str(calls),
        "MANUALS_DIR": str(manuals),
        "MANUALS_STATE_DIR": str(tmp_path / "state"),
        "SSH_HOST": "stub-host",
        "DEPLOY_PATH": "/opt/hoocon",
    }
    return env, pdf, calls


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _calls(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_sync_uploads_mirror_and_attaches_without_prune(tmp_path: Path) -> None:
    """PDF уезжают в зеркало и привязываются; локальные удаления сайт не трогают."""
    env, _pdf, calls = _setup(tmp_path)
    result = _run(env)
    assert result.returncode == 0, result.stderr
    log = _calls(calls)
    assert "stub-host:/var/www/hoocon/manuals-src/паспорт изделия/" in log
    assert "--include=*.pdf" in log
    assert "--delete" not in log
    assert "attach_manual_pdfs --dir /app/manuals-src --skip-category" in log
    assert "--dry-run" not in log
    assert "обновлено/создано PDF на сайте — 3" in result.stdout


def test_if_changed_skips_ssh_when_pdfs_unchanged(tmp_path: Path) -> None:
    """launchd дёргает скрипт каждые 5 минут — без изменений не ходим на прод."""
    env, _pdf, calls = _setup(tmp_path)
    assert _run(env).returncode == 0
    calls.unlink()
    result = _run(env, "--if-changed")
    assert result.returncode == 0, result.stderr
    assert _calls(calls) == ""


def test_if_changed_waits_until_files_settle(tmp_path: Path) -> None:
    """Файл ещё пишется (Яндекс.Диск/рендер) — не заливать полуфайл."""
    env, pdf, calls = _setup(tmp_path)
    assert _run(env).returncode == 0
    calls.unlink()
    pdf.write_bytes(b"%PDF-v2-longer")

    fresh = _run(env, "--if-changed")
    assert fresh.returncode == 0, fresh.stderr
    assert _calls(calls) == ""

    settled = _run({**env, "MANUALS_SETTLE_SEC": "0"}, "--if-changed")
    assert settled.returncode == 0, settled.stderr
    assert "attach_manual_pdfs" in _calls(calls)


def test_failed_rsync_is_not_stamped_as_synced(tmp_path: Path) -> None:
    """run() идёт в `if !`, где bash глушит set -e: упавший rsync проскакивал бы
    к attach и записывал отметку — изменённый PDF больше никогда не уехал бы.
    """
    env, _pdf, calls = _setup(tmp_path)
    failed = _run({**env, "RSYNC_EXIT": "23"})
    assert failed.returncode != 0
    assert "attach_manual_pdfs" not in _calls(calls)
    assert not (tmp_path / "state" / "manual-pdfs.sync-stamp").exists()

    calls.unlink()
    retry = _run(env, "--if-changed")
    assert retry.returncode == 0, retry.stderr
    assert "attach_manual_pdfs" in _calls(calls)


def test_dry_run_does_not_stamp(tmp_path: Path) -> None:
    """--dry-run ничего не пишет на сайт, значит и отметку ставить нельзя."""
    env, _pdf, calls = _setup(tmp_path)
    assert _run(env, "--dry-run").returncode == 0
    assert "--skip-category --dry-run" in _calls(calls)
    assert not (tmp_path / "state" / "manual-pdfs.sync-stamp").exists()


def test_prod_web_mounts_manuals_mirror_read_only() -> None:
    """attach_manual_pdfs на проде читает зеркало из /app/manuals-src."""
    compose = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    assert "/var/www/hoocon/manuals-src:/app/manuals-src:ro" in compose["services"]["web"]["volumes"]
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "WWW_MANUALS:-/var/www/hoocon/manuals-src" in deploy
    assert "'${WWW_MANUALS}'" in deploy


def test_manual_deploy_syncs_pdfs_after_smoke() -> None:
    """Ручной деплой с машины, где есть _инструкции-pdf, заодно заливает PDF."""
    deploy = (ROOT / "scripts" / "deploy-to-vps.sh").read_text(encoding="utf-8")
    assert deploy.index("SPA GET ok") < deploy.index("./scripts/sync-manual-pdfs.sh")
    assert deploy.index("./scripts/sync-manual-pdfs.sh") < deploy.index("Manual deploy OK")
