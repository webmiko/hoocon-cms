#!/usr/bin/env bash
# Exit 1 when the newest COMPLETED backup is missing or older than MAX_AGE_HOURS.
# Called by monitor-health.sh so a dead nightly backup raises the same Telegram
# alert as a dead site (it was silent for weeks: the dir stayed empty).
#
# Env: BACKUP_ROOT (default /opt/hoocon/backups), MAX_AGE_HOURS (default 26),
#      REQUIRE_OFFSITE=1 → the newest backup must also contain OFFSITE_OK.
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-${DEPLOY_PATH:-/opt/hoocon}/backups}"
MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"

newest=0
newest_dir=""
for marker in "${BACKUP_ROOT}"/*/COMPLETED; do
  [[ -f "${marker}" ]] || continue
  mtime="$(stat -c %Y "${marker}" 2>/dev/null || stat -f %m "${marker}")"
  if (( mtime > newest )); then
    newest="${mtime}"
    newest_dir="$(dirname "${marker}")"
  fi
done

if (( newest == 0 )); then
  echo "no COMPLETED backup in ${BACKUP_ROOT}"
  exit 1
fi

age_hours=$(( ($(date +%s) - newest) / 3600 ))
if (( age_hours > MAX_AGE_HOURS )); then
  echo "newest backup is ${age_hours}h old (max ${MAX_AGE_HOURS}h)"
  exit 1
fi
if [[ "${REQUIRE_OFFSITE:-0}" == "1" && ! -f "${newest_dir}/OFFSITE_OK" ]]; then
  echo "newest backup $(basename "${newest_dir}") was not copied off-site (no OFFSITE_OK)"
  exit 1
fi
echo "newest backup ${age_hours}h old"
