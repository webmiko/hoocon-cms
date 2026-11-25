#!/usr/bin/env bash
# Copy the newest local backup to an S3-compatible bucket (off the VPS).
# Called by backup-vps.sh after COMPLETED is written; also runnable by hand:
#   /opt/hoocon/scripts/backup-offsite.sh [BACKUP_DIR]
#
# Config (keys in /opt/hoocon/.env, read as text, never sourced):
#   S3_BACKUP_BUCKET            required; empty → script exits 0 and does nothing
#   S3_BACKUP_ENDPOINT          required for non-AWS providers (Reg.ru: panel → «Хранилище S3» → «Подключение»; bare host is fine)
#   S3_BACKUP_ACCESS_KEY_ID / S3_BACKUP_SECRET_ACCESS_KEY   required
#   S3_BACKUP_REGION            optional
#   S3_BACKUP_PREFIX            optional, default "hoocon"
#   S3_BACKUP_RETENTION_DAYS    optional, default 30 (remote db/ copies only)
#
# Uploaded:  db/<STAMP>/hoocon.dump + private_media.tar.gz   (small, every night)
#            media/                                           (12 GB: `copy`, incremental,
#                                                              never deletes remote files)
# Runs rclone from a pinned container image: nothing to install on the host.
# On success writes <backup dir>/OFFSITE_OK, which monitor-health.sh checks.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
BACKUP_ROOT="${BACKUP_ROOT:-${DEPLOY_PATH}/backups}"
MEDIA_PATH="${MEDIA_PATH:-/var/www/hoocon/media}"
RCLONE_IMAGE="${RCLONE_IMAGE:-rclone/rclone:1.76.0}"
ENV_FILE="${ENV_FILE:-${DEPLOY_PATH}/.env}"

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib-env.sh"

get() { hoocon_env_get "${ENV_FILE}" "$1" "${2:-}"; }

BUCKET="$(get S3_BACKUP_BUCKET)"
if [[ -z "${BUCKET}" ]]; then
  echo "offsite: S3_BACKUP_BUCKET not set, skipping" >&2
  exit 0
fi

PREFIX="$(get S3_BACKUP_PREFIX hoocon)"
RETENTION_DAYS="$(get S3_BACKUP_RETENTION_DAYS 30)"
for required in S3_BACKUP_ACCESS_KEY_ID S3_BACKUP_SECRET_ACCESS_KEY; do
  [[ -n "$(get "${required}")" ]] || { echo "offsite: ${required} missing in ${ENV_FILE}" >&2; exit 1; }
done

DIR="${1:-}"
if [[ -z "${DIR}" ]]; then
  DIR="$(ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null | head -n 1 || true)"
  DIR="${DIR%/}"
fi
[[ -n "${DIR}" && -f "${DIR}/COMPLETED" ]] || { echo "offsite: no COMPLETED backup to upload" >&2; exit 1; }
STAMP="$(basename "${DIR}")"

# Reg.ru shows the endpoint as a bare host; rclone needs a scheme.
ENDPOINT="$(get S3_BACKUP_ENDPOINT)"
if [[ -n "${ENDPOINT}" && "${ENDPOINT}" != *://* ]]; then
  ENDPOINT="https://${ENDPOINT}"
fi
REGION="$(get S3_BACKUP_REGION)"
# A mode-600 config file, mounted read-only. docker -e would put the secret
# on the host process list for anyone who can read /proc/*/cmdline.
CONF="$(mktemp "${TMPDIR:-/tmp}/hoocon-rclone.XXXXXX")"
chmod 600 "${CONF}"
trap 'rm -f "${CONF}"' EXIT
{
  printf '%s\n' "[OFFSITE]"
  printf '%s\n' "type = s3"
  printf '%s\n' "provider = Other"
  printf '%s\n' "endpoint = ${ENDPOINT}"
  printf '%s\n' "access_key_id = $(get S3_BACKUP_ACCESS_KEY_ID)"
  printf '%s\n' "secret_access_key = $(get S3_BACKUP_SECRET_ACCESS_KEY)"
  if [[ -n "${REGION}" ]]; then
    printf '%s\n' "region = ${REGION}"
  fi
} > "${CONF}"
chmod 600 "${CONF}"

rclone() {
  docker run --rm \
    -v "${CONF}:/config/rclone/rclone.conf:ro" \
    -v "${DIR}:/backup:ro" -v "${MEDIA_PATH}:/media:ro" \
    "${RCLONE_IMAGE}" "$@"
}

REMOTE="OFFSITE:${BUCKET}/${PREFIX}"
echo "==> offsite: db + private media → ${BUCKET}/${PREFIX}/db/${STAMP}"
rclone copy /backup "${REMOTE}/db/${STAMP}" \
  --include 'hoocon.dump' --include 'private_media.tar.gz' --s3-no-check-bucket
if [[ -d "${MEDIA_PATH}" ]]; then
  echo "==> offsite: media (incremental copy)"
  rclone copy /media "${REMOTE}/media" --s3-no-check-bucket --transfers 4
fi

echo "==> offsite: prune db/ copies older than ${RETENTION_DAYS}d"
rclone delete "${REMOTE}/db" --min-age "${RETENTION_DAYS}d" --rmdirs --s3-no-check-bucket

echo "${STAMP}" > "${DIR}/OFFSITE_OK"
echo "offsite finished: ${STAMP}"
