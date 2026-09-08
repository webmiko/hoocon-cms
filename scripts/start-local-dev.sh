#!/usr/bin/env bash
set -euo pipefail

# Start local backend/frontend dev servers in the background.
# Does not touch Postgres/data; assumes local DB is already available.
#
# Pinned ports for this repo (override only if needed):
#   BACKEND_PORT=8002  FRONTEND_PORT=5174
# Vite proxy target: HOCON_BACKEND_ORIGIN=http://127.0.0.1:8002
#
# Detach via Python double-fork + setsid so processes survive when the
# parent shell exits (Cursor agent turns kill the command's process group;
# plain nohup/disown in a subshell is not enough on macOS).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Canonical local ports for hoocon-cms (other local projects use 8000/5173).
BACKEND_PORT="${BACKEND_PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"
BACKEND_ORIGIN="http://127.0.0.1:${BACKEND_PORT}"

start_detached() {
  local cwd="$1"
  local log_file="$2"
  shift 2
  HOCON_CWD="${cwd}" HOCON_LOG="${log_file}" python3 - "$@" <<'PY'
import os
import sys

cwd = os.environ["HOCON_CWD"]
log = os.environ["HOCON_LOG"]
args = sys.argv[1:]
if not args:
    raise SystemExit("start_detached: missing command")

if os.fork() != 0:
    raise SystemExit(0)
os.setsid()
if os.fork() != 0:
    raise SystemExit(0)

os.chdir(cwd)
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
os.dup2(fd, 1)
os.dup2(fd, 2)
os.close(fd)
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)
os.close(devnull)
os.execvp(args[0], args)
PY
}

# Persist ports so stop-local-dev.sh matches these listeners.
printf '%s\n' "${BACKEND_PORT}" > /tmp/hoocon-backend.port
printf '%s\n' "${FRONTEND_PORT}" > /tmp/hoocon-frontend.port

if lsof -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend already listens on ${BACKEND_PORT}."
else
  start_detached "${ROOT}/backend" /tmp/hoocon-backend.log \
    poetry run python manage.py runserver "127.0.0.1:${BACKEND_PORT}"
  echo "Started backend on 127.0.0.1:${BACKEND_PORT}"
fi

if lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Frontend already listens on ${FRONTEND_PORT}."
else
  start_detached "${ROOT}/frontend" /tmp/hoocon-frontend.log \
    env HOCON_BACKEND_ORIGIN="${BACKEND_ORIGIN}" HOCON_FRONTEND_PORT="${FRONTEND_PORT}" \
    npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
  echo "Started frontend on 127.0.0.1:${FRONTEND_PORT}"
  echo "Vite proxy → ${BACKEND_ORIGIN}"
fi

echo "Logs:"
echo "  backend  -> /tmp/hoocon-backend.log"
echo "  frontend -> /tmp/hoocon-frontend.log"
echo "Admin: http://127.0.0.1:${BACKEND_PORT}/admin/"
echo "Site:  http://127.0.0.1:${FRONTEND_PORT}/"
