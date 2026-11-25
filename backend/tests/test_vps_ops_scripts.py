"""Tests for VPS ops scripts (monitor, disk cleanup, cron)."""

from __future__ import annotations

import os
import subprocess
import time
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


def _bash(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **(env or {})},
        check=False,
    )


def test_env_reader_survives_unquoted_value_with_space(tmp_path: Path) -> None:
    """Regression: `source .env` died on «ADMIN_X=Foo CMS» and stopped nightly backups."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        'ADMIN_TITLE=Hoocon CMS\nDB_USER="quoted"\nDB_NAME=plain\nDB_NAME=last_wins\n',
        encoding="utf-8",
    )
    probe = (
        f'source "{ROOT}/scripts/lib-env.sh"; '
        f'echo "$(hoocon_env_get "{env_file}" DB_USER x)|$(hoocon_env_get "{env_file}" DB_NAME x)'
        f'|$(hoocon_env_get "{env_file}" MISSING dflt)"'
    )
    result = subprocess.run(["bash", "-euo", "pipefail", "-c", probe], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "quoted|last_wins|dflt"


def test_backup_script_does_not_source_env() -> None:
    text = (ROOT / "scripts" / "backup-vps.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "source .env" not in code
    assert "hoocon_env_get" in text


def test_deploy_syncs_every_script_backup_depends_on() -> None:
    """backup-vps.sh sources backup-retention.sh and lib-env.sh; they must reach the VPS."""
    deploy = (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    backup = (ROOT / "scripts" / "backup-vps.sh").read_text(encoding="utf-8")
    monitor = (ROOT / "scripts" / "monitor-health.sh").read_text(encoding="utf-8")
    for name in ("backup-retention.sh", "lib-env.sh", "check-backup-fresh.sh"):
        assert name in backup + monitor, name
        assert f"--include='{name}'" in deploy, f"{name} is not synced to the VPS"


def _make_backup(root: Path, name: str, age_hours: float) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    marker = folder / "COMPLETED"
    marker.write_text(name, encoding="utf-8")
    stamp = time.time() - age_hours * 3600
    os.utime(marker, (stamp, stamp))


def test_backup_freshness_check_fails_on_empty_dir(tmp_path: Path) -> None:
    result = _bash("check-backup-fresh.sh", env={"BACKUP_ROOT": str(tmp_path)})
    assert result.returncode == 1
    assert "no COMPLETED backup" in result.stdout


def test_backup_freshness_check_fails_on_incomplete_and_stale(tmp_path: Path) -> None:
    (tmp_path / "20260101T000000Z").mkdir()  # no COMPLETED marker: a half-written run
    _make_backup(tmp_path, "20260102T000000Z", age_hours=30)
    result = _bash("check-backup-fresh.sh", env={"BACKUP_ROOT": str(tmp_path)})
    assert result.returncode == 1
    assert "old" in result.stdout


def test_backup_freshness_check_passes_on_recent_backup(tmp_path: Path) -> None:
    _make_backup(tmp_path, "20260102T000000Z", age_hours=30)
    _make_backup(tmp_path, "20260103T000000Z", age_hours=2)
    result = _bash("check-backup-fresh.sh", env={"BACKUP_ROOT": str(tmp_path)})
    assert result.returncode == 0, result.stdout


def _offsite_setup(tmp_path: Path, *, s3_env: str, docker_exit: int = 0) -> tuple[Path, Path, dict[str, str]]:
    """Backup dir with COMPLETED, a fake `docker` that logs argv+env, and an env file."""
    backups = tmp_path / "backups"
    _make_backup(backups, "20260201T030000Z", age_hours=1)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    fake = bin_dir / "docker"
    # Logs argv and, if present, the mounted rclone.conf (mode + body) while
    # the script still has the file. Does not record process environment:
    # secrets must not arrive via `docker -e`.
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        f"log = {str(log)!r}\n"
        "args = sys.argv[1:]\n"
        "with open(log, 'a', encoding='utf-8') as fh:\n"
        "    fh.write('ARGS: ' + ' '.join(args) + '\\n')\n"
        "    for arg in args:\n"
        "        suffix = ':/config/rclone/rclone.conf:ro'\n"
        "        if arg.endswith(suffix):\n"
        "            host = arg[: -len(suffix)]\n"
        "            mode = os.stat(host).st_mode & 0o777\n"
        "            body = open(host, encoding='utf-8').read()\n"
        "            fh.write(f'CONF_MODE:{mode:o}\\n')\n"
        "            fh.write('CONF_BODY_START\\n' + body + 'CONF_BODY_END\\n')\n"
        "    for key, value in os.environ.items():\n"
        "        if key.startswith('RCLONE_CONFIG'):\n"
        "            fh.write(f'{key}={value}\\n')\n"
        f"raise SystemExit({docker_exit})\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env_file = tmp_path / ".env"
    env_file.write_text(s3_env, encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "BACKUP_ROOT": str(backups),
        "ENV_FILE": str(env_file),
        "MEDIA_PATH": str(tmp_path / "media"),
    }
    return backups / "20260201T030000Z", log, env


S3_ENV = (
    "ADMIN_PASSKEY_RP_NAME=HOOCON CMS\n"
    "S3_BACKUP_BUCKET=my-bucket\nS3_BACKUP_ENDPOINT=https://s3.example.test\n"
    "S3_BACKUP_ACCESS_KEY_ID=AKIDEXAMPLE\nS3_BACKUP_SECRET_ACCESS_KEY=s3cr3t-value\n"
)


def test_offsite_skips_quietly_without_bucket(tmp_path: Path) -> None:
    backup, log, env = _offsite_setup(tmp_path, s3_env="ADMIN_PASSKEY_RP_NAME=HOOCON CMS\n")
    result = _bash("backup-offsite.sh", env=env)
    assert result.returncode == 0
    assert not log.exists()
    assert not (backup / "OFFSITE_OK").exists()


def test_offsite_uploads_and_marks_ok_without_secrets_in_argv(tmp_path: Path) -> None:
    backup, log, env = _offsite_setup(tmp_path, s3_env=S3_ENV)
    result = _bash("backup-offsite.sh", env=env)
    assert result.returncode == 0, result.stderr
    assert (backup / "OFFSITE_OK").read_text(encoding="utf-8").strip() == "20260201T030000Z"
    logged = log.read_text(encoding="utf-8")
    args = [line for line in logged.splitlines() if line.startswith("ARGS:")]
    assert any("copy /backup OFFSITE:my-bucket/hoocon/db/20260201T030000Z" in a for a in args)
    assert any("delete OFFSITE:my-bucket/hoocon/db --min-age 30d" in a for a in args)
    # Secret must not be on the docker command line or in the process environment.
    assert "s3cr3t-value" not in "\n".join(args)
    assert "AKIDEXAMPLE" not in "\n".join(args)
    assert "RCLONE_CONFIG" not in logged.split("CONF_BODY_START", 1)[0]
    assert "CONF_MODE:600" in logged
    body = logged.split("CONF_BODY_START\n", 1)[1].split("CONF_BODY_END", 1)[0]
    assert "secret_access_key = s3cr3t-value" in body
    assert "endpoint = https://s3.example.test" in body


def test_offsite_adds_https_to_bare_endpoint_host(tmp_path: Path) -> None:
    """Reg.ru panel shows the endpoint without a scheme; rclone needs one."""
    bare = S3_ENV.replace("https://s3.example.test", "s3.example.test")
    _backup, log, env = _offsite_setup(tmp_path, s3_env=bare)
    assert _bash("backup-offsite.sh", env=env).returncode == 0
    logged = log.read_text(encoding="utf-8")
    body = logged.split("CONF_BODY_START\n", 1)[1].split("CONF_BODY_END", 1)[0]
    assert "endpoint = https://s3.example.test" in body
    assert "endpoint = s3.example.test\n" not in body


def test_offsite_failure_leaves_no_ok_marker_and_exits_nonzero(tmp_path: Path) -> None:
    backup, _log, env = _offsite_setup(tmp_path, s3_env=S3_ENV, docker_exit=1)
    result = _bash("backup-offsite.sh", env=env)
    assert result.returncode != 0
    assert not (backup / "OFFSITE_OK").exists()


def test_offsite_rejects_missing_credentials(tmp_path: Path) -> None:
    _backup, log, env = _offsite_setup(tmp_path, s3_env="S3_BACKUP_BUCKET=my-bucket\n")
    result = _bash("backup-offsite.sh", env=env)
    assert result.returncode == 1
    assert "S3_BACKUP_ACCESS_KEY_ID missing" in result.stderr
    assert not log.exists()


def test_freshness_check_requires_offsite_marker_when_asked(tmp_path: Path) -> None:
    _make_backup(tmp_path, "20260203T030000Z", age_hours=1)
    base = {"BACKUP_ROOT": str(tmp_path)}
    assert _bash("check-backup-fresh.sh", env=base).returncode == 0
    missing = _bash("check-backup-fresh.sh", env={**base, "REQUIRE_OFFSITE": "1"})
    assert missing.returncode == 1
    assert "off-site" in missing.stdout
    (tmp_path / "20260203T030000Z" / "OFFSITE_OK").write_text("x", encoding="utf-8")
    assert _bash("check-backup-fresh.sh", env={**base, "REQUIRE_OFFSITE": "1"}).returncode == 0


def test_cron_strip_removes_only_duplicate_hoocon_jobs() -> None:
    """Regression: root crontab ran backup and monitor a second time next to /etc/cron.d."""
    crontab = (
        "# mine\n"
        "MAILTO=ops@example.test\n"
        "15 3 * * * /opt/hoocon/scripts/backup-vps.sh >> /var/log/hoocon-backup.log 2>&1\n"
        "*/5 * * * * HEALTH_URL=http://127.0.0.1:8000/api/health/ /opt/hoocon/scripts/monitor-health.sh\n"
        "0 4 * * * /usr/local/bin/other-job.sh\n"
        "# 0 5 * * * /opt/hoocon/scripts/backup-vps.sh (commented)\n"
    )
    result = subprocess.run(
        ["bash", str(ROOT / "scripts" / "cron-strip-stray.sh"), "/opt/hoocon"],
        input=crontab,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == (
        "# mine\nMAILTO=ops@example.test\n0 4 * * * /usr/local/bin/other-job.sh\n"
        "# 0 5 * * * /opt/hoocon/scripts/backup-vps.sh (commented)\n"
    )
    assert "backup-offsite.sh" in (ROOT / "scripts" / "deploy-remote.sh").read_text(encoding="utf-8")
    install = (ROOT / "scripts" / "vps-install-cron.sh").read_text(encoding="utf-8")
    assert "cron-strip-stray.sh" in install


def _run_backup(tmp_path: Path, env_text: str) -> Path:
    """Run backup-vps.sh against a fake docker; return the created backup dir."""
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / ".env").write_text(env_text, encoding="utf-8")
    media = tmp_path / "media"
    media.mkdir()
    (media / "a.jpg").write_text("x", encoding="utf-8")
    private = tmp_path / "private_media"
    private.mkdir()
    (private / "b.pdf").write_text("y", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "docker"
    fake.write_text('#!/usr/bin/env bash\n[[ "$1" == compose ]] && echo DUMP\nexit 0\n', encoding="utf-8")
    fake.chmod(0o755)
    result = _bash(
        "backup-vps.sh",
        env={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DEPLOY_PATH": str(deploy),
            "MEDIA_PATH": str(media),
            "PRIVATE_MEDIA_PATH": str(private),
        },
    )
    assert result.returncode == 0, result.stderr
    (backup,) = (deploy / "backups").iterdir()
    assert (backup / "COMPLETED").exists()
    return backup


def test_backup_keeps_local_media_tar_without_s3(tmp_path: Path) -> None:
    backup = _run_backup(tmp_path, "ADMIN_PASSKEY_RP_NAME=HOOCON CMS\n")
    assert (backup / "media.tar.gz").exists()
    assert (backup / "private_media.tar.gz").exists()


def test_backup_skips_local_media_tar_when_s3_configured(tmp_path: Path) -> None:
    """Media is copied to S3 incrementally; three nightly 12 GB tars would fill the disk."""
    backup = _run_backup(tmp_path, S3_ENV)
    assert not (backup / "media.tar.gz").exists()
    assert (backup / "private_media.tar.gz").exists()
    assert (backup / "hoocon.dump").exists()
