#!/usr/bin/env bash
# Send a deduped ops alert to Telegram (monitor-health, manual).
#
# Prefers ``docker compose exec web … ops_telegram_alert``; when the web
# container is down, falls back to curl + Bot API using DEPLOY_PATH/.env.
#
# Usage:
#   ./scripts/ops-telegram-alert.sh "health FAIL" monitor-health
set -euo pipefail

MESSAGE="${1:?message required}"
DEDUP_KEY="${2:-monitor}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
COMPOSE_FILE="${COMPOSE_FILE:-${DEPLOY_PATH}/docker-compose.yml}"
DEDUP_SECONDS="${OPS_ALERT_DEDUP_SECONDS:-900}"
STAMP_FILE="/var/run/hoocon-ops-alert-${DEDUP_KEY}"

if [[ -f "${STAMP_FILE}" ]]; then
  NOW="$(date +%s)"
  LAST="$(stat -c %Y "${STAMP_FILE}" 2>/dev/null || echo 0)"
  if (( NOW - LAST < DEDUP_SECONDS )); then
    exit 0
  fi
fi

if command -v docker >/dev/null 2>&1 \
  && docker compose -f "${COMPOSE_FILE}" ps web --status running -q 2>/dev/null | grep -q .; then
  if docker compose -f "${COMPOSE_FILE}" exec -T web \
    python manage.py ops_telegram_alert \
      --message "${MESSAGE}" \
      --dedup-key "${DEDUP_KEY}" >/dev/null 2>&1; then
    mkdir -p "$(dirname "${STAMP_FILE}")"
    touch "${STAMP_FILE}"
    exit 0
  fi
fi

ENV_FILE="${DEPLOY_PATH}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  exit 0
fi

TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '"')"
CHATS="$(grep -E '^OPS_TELEGRAM_CHAT_IDS=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '"')"
if [[ -z "${TOKEN}" || -z "${CHATS}" ]]; then
  exit 0
fi

TITLE="Hoocon monitor"
TEXT="${TITLE}: ${MESSAGE}"
IFS=',' read -r -a CHAT_IDS <<< "${CHATS}"
for CHAT in "${CHAT_IDS[@]}"; do
  CHAT="$(echo "${CHAT}" | xargs)"
  [[ -n "${CHAT}" ]] || continue
  curl -fsS --max-time 15 -X POST \
    "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d "chat_id=${CHAT}" \
    --data-urlencode "text=${TEXT}" >/dev/null || true
done

mkdir -p "$(dirname "${STAMP_FILE}")"
touch "${STAMP_FILE}"
