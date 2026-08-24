#!/usr/bin/env bash
# Ручной деплой на VPS — запасной путь, когда GitHub Actions недоступен.
# Зеркалит CI: checkup → image linux/amd64 → frontend → SSH
# (scripts/deploy-remote.sh). Канон: _docs/manual-deploy.md
#
# Usage:
#   ./scripts/deploy-to-vps.sh                 # полный цикл
#   ./scripts/deploy-to-vps.sh --checks-only   # только проверки
#   ./scripts/deploy-to-vps.sh --skip-checks   # аварийно без checkup
#   ./scripts/deploy-to-vps.sh --push-ghcr     # образ через GHCR (если есть права)
#   ./scripts/deploy-to-vps.sh --dry-run       # показать план, ничего не слать
#
# Env (optional, или .local/deploy.env):
#   SSH_HOST=hoocon-prod  DEPLOY_PATH=/opt/hoocon
#   DOCKER_PLATFORM=linux/amd64
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CHECKS_ONLY=0
SKIP_CHECKS=0
PUSH_GHCR=0
DRY_RUN=0
SKIP_FRONTEND=0

usage() {
  cat <<'USAGE'
Ручной деплой на VPS (когда GitHub Actions недоступен).
Канон: _docs/manual-deploy.md

Usage:
  ./scripts/deploy-to-vps.sh                 # полный цикл
  ./scripts/deploy-to-vps.sh --checks-only   # только проверки
  ./scripts/deploy-to-vps.sh --skip-checks   # аварийно без checkup
  ./scripts/deploy-to-vps.sh --push-ghcr     # образ через GHCR
  ./scripts/deploy-to-vps.sh --dry-run       # план без выкладки
  ./scripts/deploy-to-vps.sh -h

Env / .local/deploy.env: SSH_HOST, DEPLOY_PATH, DOCKER_PLATFORM, SMOKE_HOST
USAGE
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --checks-only) CHECKS_ONLY=1 ;;
    --skip-checks) SKIP_CHECKS=1 ;;
    --push-ghcr) PUSH_GHCR=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --skip-frontend) SKIP_FRONTEND=1 ;;
    -h|--help) usage 0 ;;
    *)
      echo -e "${RED}Unknown flag: $1${NC}" >&2
      usage 2
      ;;
  esac
  shift
done

if [[ -f "${ROOT}/.local/deploy.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/.local/deploy.env"
  set +a
fi

SSH_HOST="${SSH_HOST:-hoocon-prod}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"
REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_NAME="${IMAGE_NAME:-$(git remote get-url origin \
  | sed -E 's#.*github.com[:/]##; s#\.git$##' \
  | tr '[:upper:]' '[:lower:]')}"
GIT_SHA="$(git rev-parse HEAD)"
# Always tag current HEAD unless explicitly overridden (avoids stale shell env).
DOCKER_IMAGE="${DEPLOY_IMAGE:-${REGISTRY}/${IMAGE_NAME}:${GIT_SHA}}"

SMOKE_HOST="${SMOKE_HOST:-}"
if [[ -z "${SMOKE_HOST}" ]]; then
  # Prefer public host from SSH config HostName when available.
  SMOKE_HOST="$(ssh -G "${SSH_HOST}" 2>/dev/null | awk '/^hostname /{print $2; exit}')"
  SMOKE_HOST="${SMOKE_HOST:-${SSH_HOST}}"
fi

echo "══════════════════════════════════════════════════"
echo "  Manual deploy → ${SSH_HOST} (${DEPLOY_PATH})"
echo "  Image: ${DOCKER_IMAGE}"
echo "  Platform: ${DOCKER_PLATFORM}"
echo "  Transfer: $([[ "${PUSH_GHCR}" -eq 1 ]] && echo GHCR pull || echo docker load)"
echo "══════════════════════════════════════════════════"

# ── 1. Checks (same gate as pre-commit / CI quality) ─────────────────
if [[ "${SKIP_CHECKS}" -eq 1 ]]; then
  echo -e "${YELLOW}⚠ Skipping checkup (--skip-checks)${NC}"
else
  echo "==> pre-commit checkup"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "    (dry-run) ./scripts/pre-commit-checkup.sh"
  else
    ./scripts/pre-commit-checkup.sh
  fi
fi

if [[ "${CHECKS_ONLY}" -eq 1 ]]; then
  echo -e "${GREEN}✓ Checks only — done${NC}"
  exit 0
fi

# ── 2. Frontend ──────────────────────────────────────────────────────
if [[ "${SKIP_FRONTEND}" -eq 1 ]]; then
  echo -e "${YELLOW}⚠ Skipping frontend build${NC}"
  if [[ ! -d frontend/dist ]]; then
    echo -e "${RED}frontend/dist missing — cannot skip build${NC}" >&2
    exit 1
  fi
else
  echo "==> frontend build"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "    (dry-run) npm ci && npm run build"
  else
    (
      cd frontend
      npm ci
      npm run build
    )
  fi
fi

# ── 3. Backend image (always linux/amd64 for VPS) ────────────────────
echo "==> docker build (${DOCKER_PLATFORM})"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "    (dry-run) docker build --platform ${DOCKER_PLATFORM} …"
else
  docker build \
    --platform "${DOCKER_PLATFORM}" \
    --build-arg "GIT_SHA=${GIT_SHA}" \
    -t "${DOCKER_IMAGE}" \
    -t "${REGISTRY}/${IMAGE_NAME}:latest" \
    backend
  ARCH="$(docker image inspect "${DOCKER_IMAGE}" \
    --format '{{.Os}}/{{.Architecture}}')"
  echo "    built ${ARCH}"
  if [[ "${ARCH}" != "linux/amd64" && "${DOCKER_PLATFORM}" == "linux/amd64" ]]; then
    echo -e "${RED}ERROR: expected linux/amd64, got ${ARCH}${NC}" >&2
    exit 1
  fi
fi

# ── 4. Deliver image to VPS ──────────────────────────────────────────
IMAGE_TRANSFER="load"
if [[ "${PUSH_GHCR}" -eq 1 ]]; then
  echo "==> push to GHCR"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "    (dry-run) docker push ${DOCKER_IMAGE}"
  else
    if ! docker push "${DOCKER_IMAGE}"; then
      echo -e "${RED}GHCR push failed (need write:packages).${NC}" >&2
      echo "Retry without --push-ghcr (docker save | ssh load)." >&2
      exit 1
    fi
    docker push "${REGISTRY}/${IMAGE_NAME}:latest" || true
  fi
  IMAGE_TRANSFER="pull"
else
  echo "==> docker save | ssh ${SSH_HOST} docker load"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "    (dry-run) stream image to VPS"
  else
    docker save "${DOCKER_IMAGE}" | ssh "${SSH_HOST}" "docker load"
  fi
fi

# ── 5. Remote compose + frontend sync ────────────────────────────────
echo "==> deploy-remote.sh"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "    (dry-run) IMAGE_TRANSFER=${IMAGE_TRANSFER} ./scripts/deploy-remote.sh"
  echo -e "${GREEN}✓ Dry-run complete — nothing deployed${NC}"
  exit 0
fi

export SSH_HOST DEPLOY_PATH DOCKER_IMAGE
export IMAGE_TRANSFER
export DEPLOY_APPLY_NGINX="${DEPLOY_APPLY_NGINX:-1}"
chmod +x scripts/deploy-remote.sh
./scripts/deploy-remote.sh

# ── 6. Smoke ─────────────────────────────────────────────────────────
echo "==> smoke http://${SMOKE_HOST}/api/health/"
SMOKE_OK=0
for _ in 1 2 3 4 5 6; do
  if curl -fsS "http://${SMOKE_HOST}/api/health/"; then
    echo
    SMOKE_OK=1
    break
  fi
  sleep 5
done
if [[ "${SMOKE_OK}" -ne 1 ]]; then
  echo -e "${RED}Smoke failed for http://${SMOKE_HOST}/api/health/${NC}" >&2
  echo "Check locally: ssh ${SSH_HOST} 'curl -fsS http://127.0.0.1:8000/api/health/'" >&2
  exit 1
fi

echo -e "${GREEN}✓ Manual deploy OK (${GIT_SHA:0:12})${NC}"
