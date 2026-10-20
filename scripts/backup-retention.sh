#!/usr/bin/env bash
# Prune local backup directories. Source this; do not execute it.
#
# hoocon_prune_backups ROOT RETENTION_DAYS [KEEP_COMPLETE]
# Keeps the newest KEEP_COMPLETE directories that contain COMPLETED.
# Deletes every other directory whose mtime is older than RETENTION_DAYS,
# including incomplete runs. A fresh incomplete directory (backup in
# progress) is younger than the retention window and stays.

hoocon_prune_backups() {
  local root="${1:?backup root}"
  local retention_days="${2:?retention days}"
  local keep_complete="${3:-3}"
  local dir count=0 listing=""
  local -a protected=()

  [[ -d "${root}" ]] || return 0

  listing="$(ls -1dt "${root}"/*/ 2>/dev/null || true)"
  while IFS= read -r dir; do
    [[ -z "${dir}" ]] && continue
    dir="${dir%/}"
    if [[ -f "${dir}/COMPLETED" ]]; then
      count=$((count + 1))
      if (( count <= keep_complete )); then
        protected+=("${dir}")
      fi
    fi
  done <<< "${listing}"

  while IFS= read -r dir; do
    [[ -z "${dir}" ]] && continue
    local skip=0 kept
    if (( ${#protected[@]} > 0 )); then
      for kept in "${protected[@]}"; do
        if [[ "${kept}" == "${dir}" ]]; then
          skip=1
          break
        fi
      done
    fi
    if (( skip == 0 )); then
      rm -rf "${dir}"
    fi
  done < <(find "${root}" -mindepth 1 -maxdepth 1 -type d -mtime "+${retention_days}" 2>/dev/null || true)
}
