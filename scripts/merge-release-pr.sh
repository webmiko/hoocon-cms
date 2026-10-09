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

# Prod shows MAJOR.MINOR; PATCH is internal. A prod release must change MINOR.
public_version() {
  git show "origin/$1:backend/config/release.py" \
    | sed -nE 's/^RELEASE_VERSION = "([0-9]+\.[0-9]+)(\.[0-9]+)?"$/\1/p'
}
git fetch origin "${BASE}" "${HEAD}" --quiet
prod_public="$(public_version "${BASE}")"
next_public="$(public_version "${HEAD}")"
if [[ "${prod_public}" == "${next_public}" && "${RELEASE_ALLOW_SAME_MINOR:-}" != "1" ]]; then
  echo "Prod already shows v${prod_public}; develop is still v${next_public}.x." >&2
  echo "Run: python3 scripts/bump-release.py minor  (commit + push develop), then retry." >&2
  echo "Hotfix without a new prod label: RELEASE_ALLOW_SAME_MINOR=1 $0" >&2
  exit 1
fi
echo "Prod release v${prod_public} → v${next_public}"

echo "Waiting for checks on PR #${number}…"
gh pr checks "${number}" --watch --fail-fast

gh pr merge "${number}" --merge --delete-branch=false
echo "Merged PR #${number}. Watch the main deploy: gh run list --branch ${BASE} --limit 3"
