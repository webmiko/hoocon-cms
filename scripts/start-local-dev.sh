#!/usr/bin/env bash
set -euo pipefail

# Start local backend/frontend dev servers in the background.
# Does not touch Postgres/data; assumes local DB is already available.
#
# Detach via Python double-fork + setsid so processes survive when the
# parent shell exits (Cursor agent turns kill the command's process group;
# plain nohup/disown in a subshell is not enough on macOS).

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Backend already listens on 8000."
else
  start_detached "${ROOT}/backend" /tmp/hoocon-backend.log \
    poetry run python manage.py runserver 127.0.0.1:8000
  echo "Started backend on 127.0.0.1:8000"
fi

if lsof -iTCP:5173 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Frontend already listens on 5173."
else
  start_detached "${ROOT}/frontend" /tmp/hoocon-frontend.log \
    npm run dev -- --host 127.0.0.1 --port 5173
  echo "Started frontend on 127.0.0.1:5173"
fi

echo "Logs:"
echo "  backend  -> /tmp/hoocon-backend.log"
echo "  frontend -> /tmp/hoocon-frontend.log"
