#!/usr/bin/env bash
# Install /etc/cron.d/hoocon on the VPS (from deploy-remote.sh or manual SSH).
#
# Required: SSH_HOST — OR — SSH_USER + SERVER_HOST
# Optional: DEPLOY_PATH (default /opt/hoocon), DEPLOY_INSTALL_CRON=1
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"

if [[ "${DEPLOY_INSTALL_CRON:-1}" != "1" ]]; then
  echo "Skip cron install (DEPLOY_INSTALL_CRON=${DEPLOY_INSTALL_CRON:-})"
  exit 0
fi

if [[ -n "${SSH_HOST:-}" ]]; then
  SSH_TARGET="${SSH_HOST}"
elif [[ -n "${SSH_USER:-}" && -n "${SERVER_HOST:-}" ]]; then
  SSH_TARGET="${SSH_USER}@${SERVER_HOST}"
else
  echo "ERROR: set SSH_HOST or SSH_USER+SERVER_HOST" >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${HOME}/.ssh/known_hosts}")
CRON_SRC="${CRON_SRC:-$(cd "$(dirname "$0")/.." && pwd)/deploy/cron/hoocon-vps.cron}"

if [[ ! -f "${CRON_SRC}" ]]; then
  echo "ERROR: missing cron template ${CRON_SRC}" >&2
  exit 1
fi

mkdir -p "${HOME}/.ssh"
if [[ -n "${SERVER_HOST:-}" ]]; then
  ssh-keyscan -H "${SERVER_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true
fi

echo "Install VPS cron → ${SSH_TARGET}:/etc/cron.d/hoocon"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
DEPLOY_PATH="${DEPLOY_PATH}"
test -x "\${DEPLOY_PATH}/scripts/monitor-health.sh"
test -x "\${DEPLOY_PATH}/scripts/vps-maintenance.sh"
EOF

# Template substitution locally, copy via stdin (no extra rsync target).
sed "s|__DEPLOY_PATH__|${DEPLOY_PATH}|g" "${CRON_SRC}" | \
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" \
    "sudo tee /etc/cron.d/hoocon >/dev/null && sudo chmod 644 /etc/cron.d/hoocon"
echo "Cron installed: /etc/cron.d/hoocon"
