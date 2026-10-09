#!/usr/bin/env bash
set -euo pipefail

# Stop local dev servers without touching Postgres or project data.
# Safe to run repeatedly.
# Pinned hoocon-cms ports: backend 8002, frontend 5174
# (/tmp/hoocon-*.port from start-local-dev.sh, with the same defaults).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

_dev_pids() {
  local backend_port frontend_port pattern
  backend_port="$(cat /tmp/hoocon-backend.port 2>/dev/null || echo 8002)"
  frontend_port="$(cat /tmp/hoocon-frontend.port 2>/dev/null || echo 5174)"
  # pgrep never lists itself (``ps | rg`` matched rg's own argv → kill failed under set -e).
  for pattern in \
    "manage\.py runserver 127\.0\.0\.1:${backend_port}" \
    "node .*vite --host 127\.0\.0\.1 --port ${frontend_port}" \
    "${ROOT}/backend/\.venv/bin/celery -A config worker"; do
    pgrep -f "${pattern}" || true
  done | sort -u | tr '\n' ' ' | sed 's/ *$//'
}

PIDS="$(_dev_pids)"

if [[ -z "${PIDS}" ]]; then
  echo "Local dev servers are already stopped."
  exit 0
fi

echo "Stopping local dev servers: ${PIDS}"
# shellcheck disable=SC2086
kill ${PIDS} 2>/dev/null || true
sleep 1

REMAINING="$(_dev_pids)"
if [[ -n "${REMAINING}" ]]; then
  echo "Force stopping remaining processes: ${REMAINING}"
  # shellcheck disable=SC2086
  kill -9 ${REMAINING} 2>/dev/null || true
fi

rm -f /tmp/hoocon-backend.port /tmp/hoocon-frontend.port
echo "Local dev servers stopped."
