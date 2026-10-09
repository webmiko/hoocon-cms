#!/usr/bin/env bash
# Start backend + Vite for Playwright smoke (catalog, PDP, RFQ).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"

cleanup() {
  local pid
  for pid in $(jobs -p); do
    kill "${pid}" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

cd "${ROOT}/backend"
export CELERY_TASK_ALWAYS_EAGER="${CELERY_TASK_ALWAYS_EAGER:-true}"
# CI runs with DJANGO_DEBUG=false, where settings trust no dev origin by default.
E2E_ORIGINS="http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}"
export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-${E2E_ORIGINS}}"
export CORS_ALLOWED_ORIGINS="${CORS_ALLOWED_ORIGINS:-${E2E_ORIGINS}}"
poetry run python manage.py migrate --noinput
poetry run python manage.py seed_e2e_smoke
poetry run python manage.py runserver "127.0.0.1:${BACKEND_PORT}" &

echo "Waiting for backend /api/health/ on port ${BACKEND_PORT}..."
for attempt in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/api/health/" >/dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
  if [ "${attempt}" -eq 60 ]; then
    echo "Backend failed to become ready within 60s" >&2
    exit 1
  fi
  sleep 1
done

cd "${ROOT}/frontend"
export HOCON_BACKEND_ORIGIN="http://127.0.0.1:${BACKEND_PORT}"
export HOCON_FRONTEND_PORT="${FRONTEND_PORT}"
npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT}" --strictPort
