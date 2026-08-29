#!/usr/bin/env bash
# Free disk on VPS before any rsync (CI SSH or manual).
#
# Runs entirely over SSH with inline commands — does not need scripts on the
# host first (critical when disk is 100% full and rsync cannot write).
#
# Required: SSH_HOST — OR — SSH_USER + SERVER_HOST
# Optional:
#   DEPLOY_PATH (default /opt/hoocon)
#   DISK_MIN_FREE_MB (default 512) — abort deploy if still below after cleanup
set -euo pipefail

DISK_MIN_FREE_MB="${DISK_MIN_FREE_MB:-512}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"

if [[ -n "${SSH_HOST:-}" ]]; then
  SSH_TARGET="${SSH_HOST}"
elif [[ -n "${SSH_USER:-}" && -n "${SERVER_HOST:-}" ]]; then
  SSH_TARGET="${SSH_USER}@${SERVER_HOST}"
else
  echo "ERROR: set SSH_HOST or SSH_USER+SERVER_HOST" >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${HOME}/.ssh/known_hosts")

mkdir -p "${HOME}/.ssh"
if [[ -n "${SERVER_HOST:-}" ]]; then
  ssh-keyscan -H "${SERVER_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true
fi

echo "Free disk on ${SSH_TARGET} (need >= ${DISK_MIN_FREE_MB} MiB free on /)"
ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s <<EOF
set -euo pipefail
MIN_MB=${DISK_MIN_FREE_MB}
DEPLOY_PATH="${DEPLOY_PATH}"
BACKUP_ROOT="\${DEPLOY_PATH}/backups"
RETENTION_DAYS=3

free_mb() {
  df -BM / | awk 'NR==2 { gsub(/M/, "", \$4); print \$4 }'
}

echo "=== df before ==="
df -h /
docker system df 2>/dev/null || true

echo "=== always: spa cache + unused docker + journal ==="
rm -rf /var/cache/nginx/hoocon_spa/* 2>/dev/null || true
docker container prune -f 2>/dev/null || true
docker image prune -af 2>/dev/null || true
docker builder prune -af 2>/dev/null || true
journalctl --vacuum-size=200M 2>/dev/null || true
find /var/log -type f -name '*.gz' -mtime +14 -delete 2>/dev/null || true
apt-get clean 2>/dev/null || true

# Old nginx site backups and local DB/media backups (safe retention).
find /etc/nginx/sites-available -maxdepth 1 -name 'hoocon.bak.*' -mtime +7 \
  -delete 2>/dev/null || true
if [[ -d "\${BACKUP_ROOT}" ]]; then
  find "\${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+\${RETENTION_DAYS}" \
    -exec rm -rf {} + 2>/dev/null || true
fi

echo "=== df after ==="
df -h /
docker system df 2>/dev/null || true

if [[ "\$(free_mb)" -lt "\${MIN_MB}" ]]; then
  echo "ERROR: still only \$(free_mb) MiB free on / (need \${MIN_MB})" >&2
  du -xm /var/www/hoocon/media "\${BACKUP_ROOT}" /var/log /var/lib/docker \
    /var/cache/nginx "\${DEPLOY_PATH}" 2>/dev/null | sort -nr | head -20 || true
  exit 1
fi
echo "Cleanup OK (\$(free_mb) MiB free)"
EOF
