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


def test_vps_free_disk_uses_shared_cleanup_and_low_threshold() -> None:
    """Pre-deploy cleanup delegates to vps-disk-cleanup.sh; 512 MiB is enough for rsync."""
    text = (ROOT / "scripts" / "vps-free-disk.sh").read_text(encoding="utf-8")
    assert 'DISK_MIN_FREE_MB="${DISK_MIN_FREE_MB:-512}"' in text
    assert "vps-disk-cleanup.sh" in text
    assert "aggressive" in text


def test_deploy_remote_syncs_ops_scripts_before_cleanup() -> None:
    """Ops scripts must land on VPS before pre-deploy disk cleanup runs."""
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    assert "Sync ops scripts" in deploy
    assert "vps-disk-cleanup.sh" in deploy
    assert deploy.index("Sync ops scripts") < deploy.index("Pre-deploy disk cleanup")
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
