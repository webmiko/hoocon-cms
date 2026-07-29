#!/usr/bin/env bash
# Dump Postgres on VPS and restore into local DB (Homebrew or Compose).
# Spec: mirror of sync-db-to-vps.sh; docs/infra-reg-ru.md § backups.
#
# Usage:
#   ./scripts/sync-db-from-vps.sh                 # fresh dump from VPS → local
#   ./scripts/sync-db-from-vps.sh hoocon-prod
#   ./scripts/sync-db-from-vps.sh --from-backup   # latest /opt/hoocon/backups/*/hoocon.dump
#   ./scripts/sync-db-from-vps.sh --with-media    # also rsync VPS media → backend/media
#
# Local target (auto):
#   - Homebrew Postgres when DB_HOST is 127.0.0.1/localhost (default .env)
#   - else docker compose service ``db``
#
# After a DB-only sync, media paths may 404 until --with-media (or a manual rsync).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="${ROOT}/.deploy-tmp"
DUMP="${TMP}/hoocon-from-vps.dump"
HOST="hoocon-prod"
FROM_BACKUP=0
WITH_MEDIA=0

for arg in "$@"; do
  case "$arg" in
    --from-backup) FROM_BACKUP=1 ;;
    --with-media) WITH_MEDIA=1 ;;
    -h|--help)
      sed -n '2,22p' "$0"
      exit 0
      ;;
    *) HOST="$arg" ;;
  esac
done

mkdir -p "${TMP}"

if [[ ! -f "${ROOT}/.env" ]]; then
  echo "ERROR: ${ROOT}/.env missing" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source "${ROOT}/.env"
set +a

DB_NAME="${DB_NAME:-hoocon}"
DB_USER="${DB_USER:-hoocon}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
export PGPASSWORD="${DB_PASSWORD:-}"

PG_BIN=""
for candidate in \
  /opt/homebrew/opt/postgresql@18/bin \
  /opt/homebrew/opt/postgresql@17/bin \
  /opt/homebrew/opt/postgresql/bin \
  /usr/local/opt/postgresql@18/bin \
  /usr/lib/postgresql/16/bin
do
  if [[ -x "${candidate}/psql" ]]; then
    PG_BIN="${candidate}"
    break
  fi
done
if [[ -n "${PG_BIN}" ]]; then
  export PATH="${PG_BIN}:${PATH}"
fi

use_compose=0
case "${DB_HOST}" in
  127.0.0.1|localhost) use_compose=0 ;;
  db) use_compose=1 ;;
  *)
    if docker compose -f "${ROOT}/docker-compose.yml" ps --status running -q db 2>/dev/null | grep -q .; then
      use_compose=1
    fi
    ;;
esac

echo "==> remote dump (${HOST})"
if [[ "${FROM_BACKUP}" -eq 1 ]]; then
  REMOTE_DUMP="$(ssh "${HOST}" 'ls -1d /opt/hoocon/backups/*/hoocon.dump 2>/dev/null | tail -1')"
  if [[ -z "${REMOTE_DUMP}" ]]; then
    echo "ERROR: no backup dump on ${HOST}" >&2
    exit 1
  fi
  echo "    using backup ${REMOTE_DUMP}"
  scp "${HOST}:${REMOTE_DUMP}" "${DUMP}"
else
  ssh "${HOST}" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/hoocon
set -a
# shellcheck disable=SC1091
source .env
set +a
DB_USER="${DB_USER:-hoocon}"
DB_NAME="${DB_NAME:-hoocon}"
docker compose exec -T db \
  pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl -Fc \
  > /tmp/hoocon-from-vps.dump
ls -lh /tmp/hoocon-from-vps.dump
REMOTE
  scp "${HOST}:/tmp/hoocon-from-vps.dump" "${DUMP}"
  ssh "${HOST}" 'rm -f /tmp/hoocon-from-vps.dump'
fi
ls -lh "${DUMP}"

echo "==> restore local (${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME})"
if [[ "${use_compose}" -eq 1 ]]; then
  docker compose -f "${ROOT}/docker-compose.yml" up -d db
  docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    pg_isready -U "${DB_USER}" -d "${DB_NAME}"
  docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;"
  docker cp "${DUMP}" \
    "$(docker compose -f "${ROOT}/docker-compose.yml" ps -q db)":/tmp/hoocon-from-vps.dump
  set +e
  docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    pg_restore -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-acl \
    /tmp/hoocon-from-vps.dump
  RC=$?
  set -e
  docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    rm -f /tmp/hoocon-from-vps.dump
  docker compose -f "${ROOT}/docker-compose.yml" exec -T db \
    psql -U "${DB_USER}" -d "${DB_NAME}" -c \
    "SELECT count(*) AS sku_count FROM catalog_sku;"
else
  command -v psql >/dev/null
  command -v pg_restore >/dev/null
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -v ON_ERROR_STOP=1 \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${DB_USER}; GRANT ALL ON SCHEMA public TO public;"
  set +e
  pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --no-owner --no-acl "${DUMP}"
  RC=$?
  set -e
  psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c \
    "SELECT count(*) AS sku_count FROM catalog_sku;"
fi

# 0=ok, 1=warnings (often OK for custom format)
if [[ "${RC}" -gt 1 ]]; then
  echo "pg_restore failed with exit ${RC}" >&2
  exit "${RC}"
fi

if [[ "${WITH_MEDIA}" -eq 1 ]]; then
  MEDIA_LOCAL="${ROOT}/backend/media"
  MEDIA_REMOTE="${MEDIA_REMOTE:-/var/www/hoocon/media/}"
  mkdir -p "${MEDIA_LOCAL}"
  echo "==> rsync media ${HOST}:${MEDIA_REMOTE} → ${MEDIA_LOCAL}"
  rsync -az --info=stats2 "${HOST}:${MEDIA_REMOTE}" "${MEDIA_LOCAL}/"
  echo "Media sync finished."
else
  echo "Media not changed (pass --with-media to rsync from VPS)."
fi

echo "DB sync from VPS finished (RC=${RC})."
