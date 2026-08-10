#!/usr/bin/env bash
# Dump local Compose Postgres and restore into VPS Compose db.
# Usage: ./scripts/sync-db-to-vps.sh [hoocon-prod]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${1:-hoocon-prod}"
TMP="${ROOT}/.deploy-tmp"
DUMP="${TMP}/hoocon.dump"

mkdir -p "${TMP}"

echo "==> dump local db"
docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
  pg_dump -U hoocon -d hoocon --no-owner --no-acl -Fc > "${DUMP}"
ls -lh "${DUMP}"

echo "==> upload + restore on VPS"
scp "${DUMP}" "${HOST}:/tmp/hoocon.dump"
ssh "${HOST}" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/hoocon
set -a
# shellcheck disable=SC1091
source .env
set +a
docker compose up -d db
docker compose exec -T db pg_isready -U "$DB_USER" -d "$DB_NAME"
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;"
docker cp /tmp/hoocon.dump "$(docker compose ps -q db)":/tmp/hoocon.dump
set +e
docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl /tmp/hoocon.dump
RC=$?
set -e
# 0=ok, 1=warnings (often OK for custom format)
if [ "$RC" -gt 1 ]; then
  echo "pg_restore failed with exit $RC" >&2
  exit "$RC"
fi
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -c \
  "SELECT count(*) AS sku_count FROM catalog_sku;"
docker compose exec -T db rm -f /tmp/hoocon.dump
rm -f /tmp/hoocon.dump
REMOTE

echo "DB sync finished."
