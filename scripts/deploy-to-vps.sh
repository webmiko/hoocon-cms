#!/usr/bin/env bash
# DEPRECATED: local deploys are not used.
# Production deploy is only via GitHub Actions on push to develop/main
# (.github/workflows/ci.yml → scripts/deploy-remote.sh).
set -euo pipefail
echo "Local deploy is disabled." >&2
echo "Push to develop or main — CI/CD will deploy." >&2
echo "One-time DB sync (ops): ./scripts/sync-db-to-vps.sh" >&2
exit 1
