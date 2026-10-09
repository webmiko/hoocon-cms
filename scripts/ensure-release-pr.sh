#!/usr/bin/env bash
set -euo pipefail

# Open the single release PR develop → main when develop is ahead of main.
# Idempotent: if an open PR already exists, new develop commits land in it
# automatically, so the script only prints its URL.

BASE="${RELEASE_BASE:-main}"
HEAD="${RELEASE_HEAD:-develop}"

git fetch origin "${BASE}" "${HEAD}" --quiet

ahead="$(git rev-list --count "origin/${BASE}..origin/${HEAD}")"
if [[ "${ahead}" == "0" ]]; then
  echo "origin/${HEAD} is not ahead of origin/${BASE}; nothing to release."
  exit 0
fi

existing="$(gh pr list --base "${BASE}" --head "${HEAD}" --state open --json url --jq '.[0].url // ""')"
if [[ -n "${existing}" ]]; then
  echo "Release PR already open (${ahead} commits): ${existing}"
  exit 0
fi

title="Release: ${HEAD} → ${BASE} ($(date +%Y-%m-%d))"
body="$(printf 'Накопленные коммиты %s → %s (%s шт.):\n\n%s\n' \
  "${HEAD}" "${BASE}" "${ahead}" \
  "$(git log --no-merges --format='- %s' "origin/${BASE}..origin/${HEAD}")")"

gh pr create --base "${BASE}" --head "${HEAD}" --title "${title}" --body "${body}"
