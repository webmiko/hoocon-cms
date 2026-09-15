#!/usr/bin/env bash
# Dump local Compose Postgres and restore into VPS Compose db.
#
# Usage:
#   ./scripts/sync-db-to-vps.sh --dry-run [hoocon-prod]
#   ./scripts/sync-db-to-vps.sh --yes [hoocon-prod]
#
# Safety: requires --yes (or HOCON_SYNC_CONFIRM=1) before DROP SCHEMA on VPS.
# Always runs backup-vps.sh on the remote host before restore.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="hoocon-prod"
DRY_RUN=0
CONFIRMED=0

usage() {
  echo "Usage: $0 [--dry-run | --yes] [ssh-host]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --yes)
      CONFIRMED=1
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      HOST="$1"
      shift
      ;;
  esac
done

if [[ "${HOCON_SYNC_CONFIRM:-}" == "1" ]]; then
  CONFIRMED=1
fi

if [[ "$DRY_RUN" -eq 0 && "$CONFIRMED" -eq 0 ]]; then
  echo "ERROR: refusing to sync without --yes or HOCON_SYNC_CONFIRM=1" >&2
  echo "       This replaces the remote public schema (DROP SCHEMA CASCADE)." >&2
  usage
fi

TMP="${ROOT}/.deploy-tmp"
DUMP="${TMP}/hoocon.dump"
mkdir -p "${TMP}"

echo "==> target host: ${HOST}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY RUN: would dump local db → ${DUMP}"
  echo "DRY RUN: would scp dump to ${HOST}:/tmp/hoocon.dump"
  echo "DRY RUN: would run backup-vps.sh on ${HOST}, then DROP SCHEMA + pg_restore"
  exit 0
fi

echo "==> dump local db"
docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
  pg_dump -U hoocon -d hoocon --no-owner --no-acl -Fc > "${DUMP}"
ls -lh "${DUMP}"

echo "==> upload + restore on VPS"
scp "${DUMP}" "${HOST}:/tmp/hoocon.dump"
ssh "${HOST}" bash -s <<REMOTE
set -euo pipefail
cd /opt/hoocon
test -f .env || { echo "ERROR: /opt/hoocon/.env missing" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -z "\${DB_NAME:-}" ]]; then
  echo "ERROR: DB_NAME missing in remote .env" >&2
  exit 1
fi
echo "==> pre-restore backup on VPS"
"${DEPLOY_PATH:-/opt/hoocon}/scripts/backup-vps.sh"
docker compose up -d db
docker compose exec -T db pg_isready -U "\$DB_USER" -d "\$DB_NAME"
docker compose exec -T db psql -U "\$DB_USER" -d "\$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;"
docker cp /tmp/hoocon.dump "\$(docker compose ps -q db)":/tmp/hoocon.dump
set +e
docker compose exec -T db pg_restore -U "\$DB_USER" -d "\$DB_NAME" --no-owner --no-acl /tmp/hoocon.dump
RC=\$?
set -e
# 0=ok, 1=warnings (often OK for custom format)
if [ "\$RC" -gt 1 ]; then
  echo "pg_restore failed with exit \$RC" >&2
  exit "\$RC"
fi
docker compose exec -T db psql -U "\$DB_USER" -d "\$DB_NAME" -c \
  "SELECT count(*) AS sku_count FROM catalog_sku;"
docker compose exec -T db rm -f /tmp/hoocon.dump
rm -f /tmp/hoocon.dump
REMOTE

echo "DB sync finished."
