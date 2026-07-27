#!/usr/bin/env bash
# Smoke monitor: /api/health/ + disk usage (cron on VPS).
# Spec: docs/infra-reg-ru.md § monitoring; ПЛАН Iter 5–6 (pre-Sentry).
#
# Usage:
#   HEALTH_URL=http://127.0.0.1:8000/api/health/ ./scripts/monitor-health.sh
# Cron example (on VPS): */5 * * * * /opt/hoocon/scripts/monitor-health.sh
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health/}"
DISK_PATH="${DISK_PATH:-/}"
DISK_WARN_PCT="${DISK_WARN_PCT:-85}"
LOG_FILE="${LOG_FILE:-/var/log/hoocon-monitor.log}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log() {
  local line="[${STAMP}] $*"
  echo "${line}"
  if mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null; then
    echo "${line}" >> "${LOG_FILE}" 2>/dev/null || true
  fi
}

RC=0

if ! curl -fsS --max-time 10 "${HEALTH_URL}" >/dev/null; then
  log "FAIL health ${HEALTH_URL}"
  RC=1
else
  log "OK health ${HEALTH_URL}"
fi

if command -v df >/dev/null 2>&1; then
  USED="$(df -P "${DISK_PATH}" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
  if [[ -n "${USED}" && "${USED}" =~ ^[0-9]+$ ]]; then
    if (( USED >= DISK_WARN_PCT )); then
      log "FAIL disk ${DISK_PATH} ${USED}% (warn>=${DISK_WARN_PCT}%)"
      RC=1
    else
      log "OK disk ${DISK_PATH} ${USED}%"
    fi
  fi
fi

exit "${RC}"
