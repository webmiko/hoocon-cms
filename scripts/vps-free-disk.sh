#!/usr/bin/env bash
# Free disk on VPS before deploy (CI SSH or manual).
#
# Required: SSH_HOST — OR — SSH_USER + SERVER_HOST
# Optional: DISK_MIN_FREE_MB (default 2048) — warn if still below after cleanup
set -euo pipefail

DISK_MIN_FREE_MB="${DISK_MIN_FREE_MB:-2048}"

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

echo "=== df before ==="
df -h /
docker system df 2>/dev/null || true

free_mb() {
  df -BM / | awk 'NR==2 { gsub(/M/, "", \$4); print \$4 }'
}

if [[ "\$(free_mb)" -ge "\${MIN_MB}" ]]; then
  echo "Enough free space (\$(free_mb) MiB) — skip aggressive cleanup"
  exit 0
fi

echo "Low disk (\$(free_mb) MiB) — cleaning…"

# Broken SPA microcache (safe; repopulates on traffic).
sudo rm -rf /var/cache/nginx/hoocon_spa/* 2>/dev/null || true

# Unused Docker layers (running containers unaffected).
docker container prune -f 2>/dev/null || true
docker image prune -af 2>/dev/null || true
docker builder prune -af 2>/dev/null || true

# Logs / apt cache
sudo journalctl --vacuum-size=200M 2>/dev/null || true
sudo find /var/log -type f -name '*.gz' -mtime +14 -delete 2>/dev/null || true
sudo apt-get clean 2>/dev/null || true

echo "=== df after ==="
df -h /
docker system df 2>/dev/null || true

if [[ "\$(free_mb)" -lt "\${MIN_MB}" ]]; then
  echo "ERROR: still only \$(free_mb) MiB free on / (need \${MIN_MB})" >&2
  exit 1
fi
echo "Cleanup OK (\$(free_mb) MiB free)"
EOF
