#!/usr/bin/env bash
# Deploy from GitHub Actions runner → VPS over SSH.
# Used by .github/workflows/ci.yml (push to develop/main only).
# Local ad-hoc deploys are not supported — use CI/CD.
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?DEPLOY_PATH is required}"
SSH_USER="${SSH_USER:?SSH_USER is required}"
SERVER_HOST="${SERVER_HOST:?SERVER_HOST is required}"
DOCKER_IMAGE="${DOCKER_IMAGE:?DOCKER_IMAGE is required}"
SSH_TARGET="${SSH_USER}@${SERVER_HOST}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

WWW_FRONTEND="${WWW_FRONTEND:-/var/www/hoocon/frontend/dist}"
WWW_STATIC="${WWW_STATIC:-/var/www/hoocon/staticfiles}"
WWW_MEDIA="${WWW_MEDIA:-/var/www/hoocon/media}"

mkdir -p "${HOME}/.ssh"
ssh-keyscan -H "${SERVER_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true

echo "Sync compose files to ${SSH_TARGET}:${DEPLOY_PATH}"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "mkdir -p '${DEPLOY_PATH}' '${WWW_FRONTEND}' '${WWW_STATIC}' '${WWW_MEDIA}'"

rsync -az -e "${RSYNC_SSH}" \
  docker-compose.prod.yml \
  "${SSH_TARGET}:${DEPLOY_PATH}/docker-compose.yml"
rsync -az -e "${RSYNC_SSH}" \
  docker-compose.hub.yml \
  "${SSH_TARGET}:${DEPLOY_PATH}/docker-compose.hub.yml"

if [[ -d frontend/dist ]]; then
  echo "Sync frontend/dist → ${WWW_FRONTEND}"
  rsync -az -e "${RSYNC_SSH}" --delete frontend/dist/ \
    "${SSH_TARGET}:${WWW_FRONTEND}/"
else
  echo "ERROR: frontend/dist missing on runner" >&2
  exit 1
fi

if [[ -d deploy/nginx ]]; then
  echo "Sync and apply host nginx site"
  rsync -az -e "${RSYNC_SSH}" deploy/nginx/ \
    "${SSH_TARGET}:${DEPLOY_PATH}/deploy/nginx/"
  if [[ "${DEPLOY_APPLY_NGINX:-1}" == "1" ]]; then
    ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" \
      "cp -a /etc/nginx/sites-available/hoocon \
         /etc/nginx/sites-available/hoocon.bak.\$(date +%Y%m%d%H%M%S) 2>/dev/null || true; \
       cp '${DEPLOY_PATH}/deploy/nginx/hoocon.conf' /etc/nginx/sites-available/hoocon; \
       ln -sfn /etc/nginx/sites-available/hoocon /etc/nginx/sites-enabled/hoocon; \
       nginx -t && systemctl reload nginx && echo 'nginx reloaded'"
  fi
fi

echo "Pull image and restart stack (${DOCKER_IMAGE})"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
cd "${DEPLOY_PATH}"
test -f .env || { echo "ERROR: ${DEPLOY_PATH}/.env missing on server" >&2; exit 1; }

if [[ -n "${GHCR_TOKEN:-}" && -n "${GHCR_USER:-}" ]]; then
  echo "${GHCR_TOKEN}" | docker login ghcr.io -u "${GHCR_USER}" --password-stdin
fi

export DOCKER_IMAGE="${DOCKER_IMAGE}"
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.hub.yml)

"\${COMPOSE[@]}" pull web celery_worker
"\${COMPOSE[@]}" up -d --no-build --remove-orphans db redis web celery_worker

echo "Waiting for health..."
for i in \$(seq 1 36); do
  if curl -fsS http://127.0.0.1:8000/api/health/ >/dev/null 2>&1; then
    curl -fsS http://127.0.0.1:8000/api/health/
    echo
    "\${COMPOSE[@]}" ps
    exit 0
  fi
  sleep 5
done
echo "ERROR: /api/health/ did not become ready" >&2
"\${COMPOSE[@]}" logs --tail=80 web >&2 || true
exit 1
EOF

echo "Deploy finished."
