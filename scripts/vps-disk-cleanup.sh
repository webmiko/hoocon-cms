#!/usr/bin/env bash
# Safe disk cleanup on the VPS host (cron / pre-deploy).
#
# Usage (on VPS):
#   ./scripts/vps-disk-cleanup.sh              # light — only when disk is tight
#   ./scripts/vps-disk-cleanup.sh maintenance  # weekly cron — always run safe steps
#   ./scripts/vps-disk-cleanup.sh aggressive   # pre-deploy — maintenance + extras
#
# Env: DISK_TIGHT_PCT (default 90), DISK_TIGHT_FREE_MB (default 2048),
#      DEPLOY_PATH, BACKUP_ROOT, RETENTION_DAYS, MONITOR_LOG_MAX_MB
set -euo pipefail

MODE="${1:-light}"
DISK_PATH="${DISK_PATH:-/}"
DISK_TIGHT_PCT="${DISK_TIGHT_PCT:-90}"
DISK_TIGHT_FREE_MB="${DISK_TIGHT_FREE_MB:-2048}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
BACKUP_ROOT="${BACKUP_ROOT:-${DEPLOY_PATH}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-3}"
MONITOR_LOG_MAX_MB="${MONITOR_LOG_MAX_MB:-10}"
MONITOR_LOG="${MONITOR_LOG:-/var/log/hoocon-monitor.log}"

disk_used_pct() {
  df -P "${DISK_PATH}" | awk 'NR==2 {gsub(/%/,"",$5); print $5}'
}

disk_free_mb() {
  df -BM "${DISK_PATH}" | awk 'NR==2 {gsub(/M/,"",$4); print $4}'
}

disk_top_dirs() {
  echo "=== top disk consumers (MiB) ==="
  du -xm /var/www/hoocon/media "${BACKUP_ROOT}" /var/log /var/lib/docker \
    /var/cache/nginx "${DEPLOY_PATH}" 2>/dev/null \
    | sort -nr | head -15 || true
}

should_cleanup() {
  local used free
  used="$(disk_used_pct)"
  free="$(disk_free_mb)"
  [[ -n "${used}" && "${used}" =~ ^[0-9]+$ ]] || return 0
  [[ -n "${free}" && "${free}" =~ ^[0-9]+$ ]] || return 0
  if (( used >= DISK_TIGHT_PCT || free < DISK_TIGHT_FREE_MB )); then
    return 0
  fi
  return 1
}

run_safe_cleanup() {
  echo "==> nginx SPA microcache"
  rm -rf /var/cache/nginx/hoocon_spa/* 2>/dev/null || true

  echo "==> unused Docker layers"
  docker container prune -f 2>/dev/null || true
  docker image prune -af 2>/dev/null || true
  docker builder prune -af 2>/dev/null || true

  echo "==> logs / apt"
  journalctl --vacuum-size=200M 2>/dev/null || true
  find /var/log -type f -name '*.gz' -mtime +14 -delete 2>/dev/null || true
  apt-get clean 2>/dev/null || true
}

run_aggressive_cleanup() {
  echo "==> old nginx site backups"
  find /etc/nginx/sites-available -maxdepth 1 -name 'hoocon.bak.*' -mtime +7 \
    -delete 2>/dev/null || true

  echo "==> backup retention (${RETENTION_DAYS}d)"
  if [[ -d "${BACKUP_ROOT}" ]]; then
    find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
      -exec rm -rf {} + 2>/dev/null || true
  fi

  if [[ -f "${MONITOR_LOG}" ]]; then
    local max_bytes=$((MONITOR_LOG_MAX_MB * 1024 * 1024))
    local size
    size="$(stat -c%s "${MONITOR_LOG}" 2>/dev/null || echo 0)"
    if (( size > max_bytes )); then
      echo "==> truncate ${MONITOR_LOG} (${size} bytes)"
      : > "${MONITOR_LOG}"
    fi
  fi
}

echo "vps-disk-cleanup mode=${MODE} path=${DISK_PATH}"
echo "=== df before ==="
df -h "${DISK_PATH}"
docker system df 2>/dev/null || true

case "${MODE}" in
  light)
    if should_cleanup; then
      echo "Disk tight (used=$(disk_used_pct)% free=$(disk_free_mb)MiB) — cleaning"
      run_safe_cleanup
    else
      echo "Disk OK (used=$(disk_used_pct)% free=$(disk_free_mb)MiB) — skip light cleanup"
    fi
    ;;
  maintenance)
    run_safe_cleanup
    run_aggressive_cleanup
    ;;
  aggressive)
    run_safe_cleanup
    run_aggressive_cleanup
    ;;
  *)
    echo "ERROR: unknown mode ${MODE} (light|maintenance|aggressive)" >&2
    exit 1
    ;;
esac

echo "=== df after ==="
df -h "${DISK_PATH}"
docker system df 2>/dev/null || true
disk_top_dirs
