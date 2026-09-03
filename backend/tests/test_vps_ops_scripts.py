"""Tests for VPS ops scripts (monitor, disk cleanup, cron)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_monitor_health_checks_spa_get_and_disk_free() -> None:
    """Cron monitor must catch half-dead prod (health ok, SPA GET fail) and low disk."""
    text = (ROOT / "scripts" / "monitor-health.sh").read_text(encoding="utf-8")
    assert "api/health" in text
    assert '<div id="root">' in text
    assert "DISK_WARN_PCT" in text
    assert "DISK_WARN_FREE_MB" in text
    assert 'DISK_WARN_PCT="${DISK_WARN_PCT:-80}"' in text
    assert "SPA_MARKER" in text


def test_vps_disk_cleanup_has_modes_and_top_dirs() -> None:
    """Shared cleanup supports light/maintenance/aggressive + du report."""
    text = (ROOT / "scripts" / "vps-disk-cleanup.sh").read_text(encoding="utf-8")
    assert "hoocon_spa" in text
    assert "maintenance" in text
    assert "aggressive" in text
    assert "top disk consumers" in text
    assert "RETENTION_DAYS" in text


def test_vps_free_disk_uses_inline_cleanup_always() -> None:
    """Pre-deploy cleanup is inline SSH (works at 100% full) and always prunes."""
    text = (ROOT / "scripts" / "vps-free-disk.sh").read_text(encoding="utf-8")
    assert 'DISK_MIN_FREE_MB="${DISK_MIN_FREE_MB:-512}"' in text
    assert "docker image prune" in text
    assert "hoocon_spa" in text
    assert "does not need scripts on the" in text or "inline" in text.lower()


def test_deploy_remote_cleans_disk_before_rsync() -> None:
    """Ops scripts must not rsync before disk cleanup (100% full blocks write)."""
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "Pre-deploy disk cleanup" in deploy
    assert "Sync ops scripts" in deploy
    assert deploy.index("Pre-deploy disk cleanup") < deploy.index("Sync ops scripts")
    assert "vps-install-cron.sh" in deploy


def test_cron_template_runs_monitor_and_maintenance() -> None:
    """Installed cron covers 5-min health/SPA/disk and weekly maintenance."""
    cron = (ROOT / "deploy/cron/hoocon-vps.cron").read_text(encoding="utf-8")
    assert "monitor-health.sh" in cron
    assert "vps-maintenance.sh" in cron
    assert "*/5" in cron
    install = (ROOT / "scripts" / "vps-install-cron.sh").read_text(encoding="utf-8")
    assert "/etc/cron.d/hoocon" in install
    assert "__DEPLOY_PATH__" in cron
