#!/usr/bin/env bash
set -euo pipefail

# Start local backend/frontend dev servers in the background.
# Does not touch Postgres/data; assumes local DB is already available.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

start_detached() {
  local log_file="$1"
  shift
  nohup "$@" </dev/null >"${log_file}" 2>&1 &
  disown
}

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend already listens on 8000."
else
  (
    cd "${ROOT}/backend"
    start_detached /tmp/hoocon-backend.log poetry run python manage.py runserver 127.0.0.1:8000
  )
  echo "Started backend on 127.0.0.1:8000"
fi

if lsof -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Frontend already listens on 5173."
else
  (
    cd "${ROOT}/frontend"
    start_detached /tmp/hoocon-frontend.log npm run dev -- --host 127.0.0.1 --port 5173
  )
  echo "Started frontend on 127.0.0.1:5173"
fi

echo "Logs:"
echo "  backend  -> /tmp/hoocon-backend.log"
echo "  frontend -> /tmp/hoocon-frontend.log"
