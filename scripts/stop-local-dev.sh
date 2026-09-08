#!/usr/bin/env bash
set -euo pipefail

# Stop local dev servers without touching Postgres or project data.
# Safe to run repeatedly.
# Pinned hoocon-cms ports: backend 8002, frontend 5174
# (/tmp/hoocon-*.port from start-local-dev.sh, with the same defaults).

_dev_pids() {
  local backend_port frontend_port
  backend_port="$(cat /tmp/hoocon-backend.port 2>/dev/null || echo 8002)"
  frontend_port="$(cat /tmp/hoocon-frontend.port 2>/dev/null || echo 5174)"
  # rg exits 1 when nothing matches — do not fail the script under pipefail.
  ps aux | rg "manage\.py runserver 127\.0\.0\.1:${backend_port}|node .*vite --host 127\.0\.0\.1 --port ${frontend_port}" \
    | awk '{print $2}' || true
}

PIDS="$(_dev_pids)"

if [[ -z "${PIDS}" ]]; then
  echo "Local dev servers are already stopped."
  exit 0
fi

echo "Stopping local dev servers: ${PIDS}"
# shellcheck disable=SC2086
kill ${PIDS}
sleep 1

REMAINING="$(_dev_pids)"
if [[ -n "${REMAINING}" ]]; then
  echo "Force stopping remaining processes: ${REMAINING}"
  # shellcheck disable=SC2086
  kill -9 ${REMAINING}
fi

rm -f /tmp/hoocon-backend.port /tmp/hoocon-frontend.port
echo "Local dev servers stopped."
