#!/usr/bin/env bash
# Weekly VPS maintenance — safe cleanup + disk report (cron on hoocon-prod).
#
# Cron (installed by vps-install-cron.sh):
#   15 3 * * 0 root /opt/hoocon/scripts/vps-maintenance.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="${LOG_FILE:-/var/log/hoocon-maintenance.log}"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

exec >> "${LOG_FILE}" 2>&1
echo "[${STAMP}] vps-maintenance start"

"${ROOT}/scripts/vps-disk-cleanup.sh" maintenance

echo "[${STAMP}] vps-maintenance done"
