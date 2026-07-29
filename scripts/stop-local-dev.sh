#!/usr/bin/env bash
set -euo pipefail

# Stop local dev servers without touching Postgres or project data.
# Safe to run repeatedly.

PIDS="$(ps aux | rg "manage\.py runserver 127\.0\.0\.1:8000|node .*vite --host 127\.0\.0\.1 --port 5173" | awk '{print $2}')"

if [[ -z "${PIDS}" ]]; then
  echo "Local dev servers are already stopped."
  exit 0
fi

echo "Stopping local dev servers: ${PIDS}"
kill ${PIDS}
sleep 1

REMAINING="$(ps aux | rg "manage\.py runserver 127\.0\.0\.1:8000|node .*vite --host 127\.0\.0\.1 --port 5173" | awk '{print $2}')"
if [[ -n "${REMAINING}" ]]; then
  echo "Force stopping remaining processes: ${REMAINING}"
  kill -9 ${REMAINING}
fi

echo "Local dev servers stopped."
