#!/usr/bin/env bash
# Install /etc/logrotate.d/hoocon-logs on the VPS (from deploy-remote or SSH).
#
# Required: SSH_HOST — OR — SSH_USER + SERVER_HOST
set -euo pipefail

if [[ -n "${SSH_HOST:-}" ]]; then
  SSH_TARGET="${SSH_HOST}"
elif [[ -n "${SSH_USER:-}" && -n "${SERVER_HOST:-}" ]]; then
  SSH_TARGET="${SSH_USER}@${SERVER_HOST}"
else
  echo "ERROR: set SSH_HOST or SSH_USER+SERVER_HOST" >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")
LOGROTATE_SRC="${LOGROTATE_SRC:-$(cd "$(dirname "$0")/.." && pwd)/deploy/logrotate/hoocon-logs}"

if [[ ! -f "${LOGROTATE_SRC}" ]]; then
  echo "ERROR: missing ${LOGROTATE_SRC}" >&2
  exit 1
fi

echo "Install logrotate → ${SSH_TARGET}:/etc/logrotate.d/hoocon-logs"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "sudo tee /etc/logrotate.d/hoocon-logs >/dev/null" < "${LOGROTATE_SRC}"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "sudo chmod 644 /etc/logrotate.d/hoocon-logs"
echo "Logrotate installed: /etc/logrotate.d/hoocon-logs"
