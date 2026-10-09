# shellcheck shell=bash
# Sourced by deploy/VPS scripts: sets SSH_OPTS with a pinned VPS host key.
#
# SSH_KNOWN_HOSTS (CI secret — `ssh-keyscan -H <host>` output, verified once
# against the VPS console) → StrictHostKeyChecking=yes.
# In GitHub Actions the secret is required: a fresh runner has no known_hosts,
# so trust-on-first-use would accept whatever key answers.
# Local runs without it trust the key on first use and never re-scan, so a
# changed key fails loudly instead of being appended silently.

hoocon_ssh_trust() {
  local known="${HOME}/.ssh/known_hosts"
  mkdir -p "${HOME}/.ssh"
  if [[ -n "${SSH_KNOWN_HOSTS:-}" ]]; then
    printf '%s\n' "${SSH_KNOWN_HOSTS}" >> "${known}"
    SSH_OPTS=(-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${known}")
    return
  fi
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
    echo "::error::SSH_KNOWN_HOSTS secret is not set — refusing to trust the VPS host key on first use." >&2
    return 1
  fi
  if [[ -n "${SERVER_HOST:-}" ]] && ! ssh-keygen -F "${SERVER_HOST}" -f "${known}" >/dev/null 2>&1; then
    ssh-keyscan -H "${SERVER_HOST}" >> "${known}" 2>/dev/null || true
  fi
  SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="${known}")
}
