#!/usr/bin/env bash
# Smoke monitor: API health + SPA GET + disk (cron on VPS).
# Spec: docs/infra-reg-ru.md § monitoring; ПЛАН Iter 5–6 (pre-Sentry).
#
# Usage:
#   ./scripts/monitor-health.sh
# Cron (via /etc/cron.d/hoocon): */5 * * * * …/monitor-health.sh >> /var/log/hoocon-monitor.log
#
# Env:
#   HEALTH_URL   — default http://127.0.0.1:8000/api/health/
#   SPA_URL      — default http://127.0.0.1/ (nginx break-glass @spa)
#   SPA_MARKER   — default <div id="root">
#   DISK_PATH    — default /
#   DISK_WARN_PCT — default 80 (used %)
#   DISK_WARN_FREE_MB — default 5120 (5 GiB free on /)
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health/}"
SPA_URL="${SPA_URL:-http://127.0.0.1/}"
SPA_MARKER=${SPA_MARKER:-'<div id="root">'}
DISK_PATH="${DISK_PATH:-/}"
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
DISK_WARN_FREE_MB="${DISK_WARN_FREE_MB:-5120}"
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

if ! curl -fsS --max-time 15 --http1.1 "${SPA_URL}" | grep -qF "${SPA_MARKER}"; then
  log "FAIL spa GET ${SPA_URL} (marker missing)"
  RC=1
else
  log "OK spa GET ${SPA_URL}"
fi

if command -v df >/dev/null 2>&1; then
  USED="$(df -P "${DISK_PATH}" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
  FREE_MB="$(df -BM "${DISK_PATH}" | awk 'NR==2 {gsub(/M/,"",$4); print $4}')"
  if [[ -n "${USED}" && "${USED}" =~ ^[0-9]+$ ]]; then
    if (( USED >= DISK_WARN_PCT )); then
      log "FAIL disk ${DISK_PATH} ${USED}% used (warn>=${DISK_WARN_PCT}%)"
      RC=1
    elif [[ -n "${FREE_MB}" && "${FREE_MB}" =~ ^[0-9]+$ && FREE_MB -lt DISK_WARN_FREE_MB ]]; then
      log "FAIL disk ${DISK_PATH} ${FREE_MB}MiB free (warn<${DISK_WARN_FREE_MB}MiB)"
      RC=1
    else
      log "OK disk ${DISK_PATH} ${USED}% used ${FREE_MB}MiB free"
    fi
  fi
fi

exit "${RC}"
