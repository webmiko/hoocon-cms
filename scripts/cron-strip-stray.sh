#!/usr/bin/env bash
# stdin: a crontab; stdout: the same minus hand-added lines that run Hoocon ops
# scripts under DEPLOY_PATH. /etc/cron.d/hoocon (from deploy/cron) is the only
# owner of those jobs; a second copy in root's crontab ran backup and monitor twice.
# Usage: crontab -l | cron-strip-stray.sh /opt/hoocon | crontab -
set -euo pipefail
DEPLOY_PATH="${1:?deploy path}"
grep -vE "^[^#]*${DEPLOY_PATH}/scripts/(backup-vps|monitor-health)\.sh" || true
