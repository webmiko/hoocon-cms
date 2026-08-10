#!/usr/bin/env bash
# Backup Postgres + media on the VPS host (run via cron on hoocon-prod).
# Spec: docs/infra-reg-ru.md § backups; ПЛАН Iter 5.
#
# Usage (on VPS):
#   /opt/hoocon/scripts/backup-vps.sh
# Or from laptop:
#   ssh hoocon-prod '/opt/hoocon/scripts/backup-vps.sh'
#
# Env overrides:
#   DEPLOY_PATH=/opt/hoocon  BACKUP_ROOT=...  RETENTION_DAYS=3  MEDIA_PATH=...
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
BACKUP_ROOT="${BACKUP_ROOT:-${DEPLOY_PATH}/backups}"
MEDIA_PATH="${MEDIA_PATH:-/var/www/hoocon/media}"
RETENTION_DAYS="${RETENTION_DAYS:-3}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${BACKUP_ROOT}/${STAMP}"

cd "${DEPLOY_PATH}"
test -f .env || { echo "ERROR: ${DEPLOY_PATH}/.env missing" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a

DB_USER="${DB_USER:-hoocon}"
DB_NAME="${DB_NAME:-hoocon}"

mkdir -p "${DEST}"
echo "==> backup ${STAMP} → ${DEST}"

echo "==> pg_dump"
docker compose exec -T db \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl -Fc \
  > "${DEST}/hoocon.dump"
ls -lh "${DEST}/hoocon.dump"

if [[ -d "${MEDIA_PATH}" ]]; then
  echo "==> media tar (${MEDIA_PATH})"
  tar -C "$(dirname "${MEDIA_PATH}")" -czf "${DEST}/media.tar.gz" \
    "$(basename "${MEDIA_PATH}")"
  ls -lh "${DEST}/media.tar.gz"
else
  echo "WARN: media path missing (${MEDIA_PATH}); skip media" >&2
fi

echo "${STAMP}" > "${DEST}/COMPLETED"
echo "==> prune older than ${RETENTION_DAYS} days"
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${RETENTION_DAYS}" \
  -exec rm -rf {} +

echo "Backup finished: ${DEST}"
