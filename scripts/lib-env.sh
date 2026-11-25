#!/usr/bin/env bash
# Read single keys from a dotenv file WITHOUT executing it. Source this.
#
# `source .env` runs every line as shell: one unquoted value with a space
# (ADMIN_X=Foo CMS) aborts a `set -e` script with «CMS: command not found».
# That silently stopped nightly backups. docker compose and Django parse
# dotenv themselves, so scripts only need a few keys, read as plain text.
#
# hoocon_env_get FILE KEY [DEFAULT]  → prints the value (last assignment wins,
# one pair of surrounding quotes removed); prints DEFAULT when absent.

hoocon_env_get() {
  local file="${1:?env file}" key="${2:?key}" default="${3:-}"
  local line value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "${file}" 2>/dev/null | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    printf '%s' "${default}"
    return 0
  fi
  value="${line#*=}"
  if [[ "${value}" =~ ^\"(.*)\"[[:space:]]*$ ]] || [[ "${value}" =~ ^\'(.*)\'[[:space:]]*$ ]]; then
    value="${BASH_REMATCH[1]}"
  fi
  printf '%s' "${value}"
}
