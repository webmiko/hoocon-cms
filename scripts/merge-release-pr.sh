#!/usr/bin/env bash
set -euo pipefail

# Merge the whole open release PR develop → main (merge commit, all commits).
# Refuses to merge while required checks are failing or pending.

BASE="${RELEASE_BASE:-main}"
HEAD="${RELEASE_HEAD:-develop}"

number="$(gh pr list --base "${BASE}" --head "${HEAD}" --state open --json number --jq '.[0].number // ""')"
if [[ -z "${number}" ]]; then
  echo "No open release PR ${HEAD} → ${BASE}. Run ./scripts/ensure-release-pr.sh first." >&2
  exit 1
fi

# Prod shows MAJOR.MINOR.PATCH. A release must change the full version.
# PATCH — a fix of a feature already shipped. MINOR — a new feature.
# MAJOR — only by hand. Same version as prod is refused.
full_version() {
  git show "origin/$1:backend/config/release.py" \
    | sed -nE 's/^RELEASE_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$/\1/p'
}
git fetch origin "${BASE}" "${HEAD}" --quiet
prod_version="$(full_version "${BASE}")"
next_version="$(full_version "${HEAD}")"
allow_same="${RELEASE_ALLOW_SAME_VERSION:-${RELEASE_ALLOW_SAME_MINOR:-}}"
if [[ "${prod_version}" == "${next_version}" && "${allow_same}" != "1" ]]; then
  echo "Prod is already v${prod_version}; develop is still v${next_version}." >&2
  echo "Fix of a shipped feature: python3 scripts/bump-release.py patch" >&2
  echo "New feature: python3 scripts/bump-release.py minor" >&2
  echo "Then commit, push develop, and retry. MAJOR only by hand." >&2
  exit 1
fi
echo "Prod release v${prod_version} → v${next_version}"

echo "Waiting for checks on PR #${number}…"
gh pr checks "${number}" --watch --fail-fast

gh pr merge "${number}" --merge --delete-branch=false
echo "Merged PR #${number}. Watch the main deploy: gh run list --branch ${BASE} --limit 3"
