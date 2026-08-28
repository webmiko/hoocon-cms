#!/usr/bin/env bash
# Deploy web image + frontend to VPS over SSH.
#
# Callers:
#   - GitHub Actions (.github/workflows/ci.yml) — IMAGE_TRANSFER=pull (GHCR)
#   - Local fallback (scripts/deploy-to-vps.sh) — IMAGE_TRANSFER=load
#
# Required env:
#   DEPLOY_PATH, DOCKER_IMAGE
#   SSH_HOST  — OR — SSH_USER + SERVER_HOST
# Optional:
#   IMAGE_TRANSFER=pull|load (default pull)
#   GHCR_USER + GHCR_TOKEN — login before pull
#   DEPLOY_APPLY_NGINX=1 (default)
#   DEPLOY_EXPORT_REDIRECTS=1 (default) — after health, rebuild /etc/nginx/redirects.map from DB
#   IMAGE_KEEP=3 — max ghcr app image tags/IDs kept on VPS after deploy
#   WWW_FRONTEND / WWW_STATIC / WWW_MEDIA
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:?DEPLOY_PATH is required}"
DOCKER_IMAGE="${DOCKER_IMAGE:?DOCKER_IMAGE is required}"
IMAGE_TRANSFER="${IMAGE_TRANSFER:-pull}"
IMAGE_KEEP="${IMAGE_KEEP:-3}"

if [[ -n "${SSH_HOST:-}" ]]; then
  SSH_TARGET="${SSH_HOST}"
elif [[ -n "${SSH_USER:-}" && -n "${SERVER_HOST:-}" ]]; then
  SSH_TARGET="${SSH_USER}@${SERVER_HOST}"
else
  echo "ERROR: set SSH_HOST or SSH_USER+SERVER_HOST" >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
RSYNC_SSH="ssh ${SSH_OPTS[*]}"

WWW_FRONTEND="${WWW_FRONTEND:-/var/www/hoocon/frontend/dist}"
WWW_STATIC="${WWW_STATIC:-/var/www/hoocon/staticfiles}"
WWW_MEDIA="${WWW_MEDIA:-/var/www/hoocon/media}"

mkdir -p "${HOME}/.ssh"
if [[ -n "${SERVER_HOST:-}" ]]; then
  ssh-keyscan -H "${SERVER_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true
fi

echo "Sync compose files to ${SSH_TARGET}:${DEPLOY_PATH}"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" \
  "mkdir -p '${DEPLOY_PATH}' '${WWW_FRONTEND}' '${WWW_STATIC}' '${WWW_MEDIA}'"

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
  echo "ERROR: frontend/dist missing" >&2
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
       if [[ -f '${DEPLOY_PATH}/deploy/nginx/hoocon-site.inc' ]]; then \
         cp '${DEPLOY_PATH}/deploy/nginx/hoocon-site.inc' /etc/nginx/hoocon-site.inc; \
       fi; \
       if [[ -f '${DEPLOY_PATH}/deploy/nginx/redirects.map' ]]; then \
         cp '${DEPLOY_PATH}/deploy/nginx/redirects.map' /etc/nginx/redirects.map; \
       fi; \
       if [[ -f '${DEPLOY_PATH}/deploy/nginx/admin-allow.conf.example' \
             && ! -f /etc/nginx/admin-allow.conf ]]; then \
         cp '${DEPLOY_PATH}/deploy/nginx/admin-allow.conf.example' \
           /etc/nginx/admin-allow.conf.example; \
       fi; \
       mkdir -p /var/cache/nginx/hoocon_spa; \
       chown www-data:www-data /var/cache/nginx/hoocon_spa 2>/dev/null || true; \
       if [[ \"\${DEPLOY_PURGE_SPA_CACHE:-1}\" == \"1\" ]]; then \
         find /var/cache/nginx/hoocon_spa -mindepth 1 -delete 2>/dev/null \
           || rm -rf /var/cache/nginx/hoocon_spa/* 2>/dev/null || true; \
         echo 'purged hoocon_spa proxy_cache'; \
       fi; \
       ln -sfn /etc/nginx/sites-available/hoocon /etc/nginx/sites-enabled/hoocon; \
       SSLIP_DOMAIN=\"\$(grep -E '^VPS_SSLIP_DOMAIN=' '${DEPLOY_PATH}/.env' 2>/dev/null \
         | tail -1 | cut -d= -f2- | tr -d '\"' | tr -d \"'\" | xargs || true)\"; \
       if [[ -n \"\${SSLIP_DOMAIN}\" \
             && -f '${DEPLOY_PATH}/deploy/nginx/hoocon-sslip-ssl.conf' \
             && -f \"/etc/letsencrypt/live/\${SSLIP_DOMAIN}/fullchain.pem\" ]]; then \
         sed \"s/203.0.113.10.sslip.io/\${SSLIP_DOMAIN}/g\" \
           '${DEPLOY_PATH}/deploy/nginx/hoocon-sslip-ssl.conf' \
           > /etc/nginx/sites-available/hoocon-sslip-ssl; \
         ln -sfn /etc/nginx/sites-available/hoocon-sslip-ssl \
           /etc/nginx/sites-enabled/hoocon-sslip-ssl; \
       fi; \
       nginx -t && systemctl reload nginx && echo 'nginx reloaded'"
  fi
fi

echo "Restart stack (${DOCKER_IMAGE}, transfer=${IMAGE_TRANSFER})"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
cd "${DEPLOY_PATH}"
test -f .env || { echo "ERROR: ${DEPLOY_PATH}/.env missing on server" >&2; exit 1; }

if [[ "${IMAGE_TRANSFER}" == "pull" ]]; then
  if [[ -n "${GHCR_TOKEN:-}" && -n "${GHCR_USER:-}" ]]; then
    echo "${GHCR_TOKEN:-}" | docker login ghcr.io -u "${GHCR_USER:-}" --password-stdin
  fi
fi

export DOCKER_IMAGE="${DOCKER_IMAGE}"
# Persist tag so compose restarts / reboot keep the same image.
if grep -q '^DOCKER_IMAGE=' .env 2>/dev/null; then
  sed -i "s|^DOCKER_IMAGE=.*|DOCKER_IMAGE=${DOCKER_IMAGE}|" .env
else
  printf '\nDOCKER_IMAGE=%s\n' "${DOCKER_IMAGE}" >> .env
fi

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.hub.yml)

if [[ "${IMAGE_TRANSFER}" == "pull" ]]; then
  "\${COMPOSE[@]}" pull web celery_worker celery_beat
elif [[ "${IMAGE_TRANSFER}" == "load" ]]; then
  docker image inspect "${DOCKER_IMAGE}" >/dev/null \
    || { echo "ERROR: image ${DOCKER_IMAGE} not on host (docker load first)" >&2; exit 1; }
  echo "Using locally loaded image (skip pull)"
else
  echo "ERROR: IMAGE_TRANSFER must be pull or load" >&2
  exit 1
fi

"\${COMPOSE[@]}" up -d --no-build --remove-orphans db redis web celery_worker celery_beat

echo "Waiting for health..."
HEALTHY=0
for i in \$(seq 1 36); do
  if curl -fsS http://127.0.0.1:8000/api/health/ >/dev/null 2>&1; then
    curl -fsS http://127.0.0.1:8000/api/health/
    echo
    "\${COMPOSE[@]}" ps
    HEALTHY=1
    break
  fi
  sleep 5
done
if [[ "\${HEALTHY}" -ne 1 ]]; then
  echo "ERROR: /api/health/ did not become ready" >&2
  "\${COMPOSE[@]}" logs --tail=80 web >&2 || true
  exit 1
fi

# Refresh nginx redirects.map from live DB (repo stub can lag after Admin/ETL).
# Opt out: DEPLOY_EXPORT_REDIRECTS=0
if [[ "${DEPLOY_EXPORT_REDIRECTS:-1}" == "1" ]]; then
  echo "Export redirects.map from DB → /etc/nginx/redirects.map"
  "\${COMPOSE[@]}" exec -T web \\
    python manage.py export_nginx_redirects --output /tmp/hoocon-redirects.map
  WEB_CID="\$("\${COMPOSE[@]}" ps -q web)"
  docker cp "\${WEB_CID}:/tmp/hoocon-redirects.map" /etc/nginx/redirects.map
  nginx -t && systemctl reload nginx && echo "nginx redirects.map reloaded"
fi

# Keep newest IMAGE_KEEP unique image IDs for this repo; drop older tags.
REPO="\${DOCKER_IMAGE%%:*}"
KEEP="${IMAGE_KEEP}"
echo "Prune \${REPO} images (keep \${KEEP} newest IDs)"
mapfile -t IDS < <(
  docker images "\${REPO}" --format '{{.CreatedAt}}|{{.ID}}' \
    | sort -r \
    | cut -d'|' -f2 \
    | awk '!seen[\$0]++'
)
if (( \${#IDS[@]} > KEEP )); then
  for id in "\${IDS[@]:KEEP}"; do
    while read -r ref; do
      [[ -n "\${ref}" ]] || continue
      echo "rmi \${ref}"
      docker rmi "\${ref}" || true
    done < <(
      docker images "\${REPO}" --format '{{.ID}} {{.Repository}}:{{.Tag}}' \
        | awk -v id="\${id}" '\$1 == id { print \$2 }'
    )
  done
fi
docker image prune -f >/dev/null || true
EOF

echo "Deploy finished."
