#!/usr/bin/env bash
# Залить локальные PDF инструкций и паспортов на прод и привязать к SKU.
#
# rsync зеркалит RU/, EN/ и «паспорт изделия»/ (только *.pdf) из
# _инструкции-pdf в WWW_MANUALS на VPS (web видит его как /app/manuals-src:ro),
# затем attach_manual_pdfs перезаливает ProductFile, у которых сменились байты
# (sha256). Удалённые локально PDF с сайта не снимаются.
#
# Usage:
#   ./scripts/sync-manual-pdfs.sh               # залить и привязать
#   ./scripts/sync-manual-pdfs.sh --dry-run     # залить зеркало, attach --dry-run
#   ./scripts/sync-manual-pdfs.sh --if-changed  # для launchd: тихо выйти, если не менялось
#
# Env / .local/deploy.env:
#   SSH_HOST=hoocon-prod  DEPLOY_PATH=/opt/hoocon
#   MANUALS_DIR=<repo>/_инструкции-pdf  WWW_MANUALS=/var/www/hoocon/manuals-src
#   MANUALS_SETTLE_SEC=60 — не заливать, пока файлы ещё пишутся (Яндекс.Диск, рендер)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

DRY_RUN=0
IF_CHANGED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --if-changed) IF_CHANGED=1 ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

if [[ -f "${ROOT}/.local/deploy.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${ROOT}/.local/deploy.env"
  set +a
fi

SSH_HOST="${SSH_HOST:-hoocon-prod}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/hoocon}"
WWW_MANUALS="${WWW_MANUALS:-/var/www/hoocon/manuals-src}"
MANUALS_DIR="${MANUALS_DIR:-${ROOT}/_инструкции-pdf}"
MANUALS_SETTLE_SEC="${MANUALS_SETTLE_SEC:-60}"
STATE_DIR="${MANUALS_STATE_DIR:-${ROOT}/.local}"
STAMP="${STATE_DIR}/manual-pdfs.sync-stamp"
LOCK="${STATE_DIR}/manual-pdfs.sync.lock"
SUBDIRS=("RU" "EN" "паспорт изделия")

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

notify() {
  [[ "${IF_CHANGED}" -eq 1 ]] && command -v osascript >/dev/null || return 0
  osascript -e "display notification \"$1\" with title \"Hoocon: мануалы\"" || true
}

if [[ ! -d "${MANUALS_DIR}" ]]; then
  log "ERROR: нет каталога ${MANUALS_DIR}" >&2
  exit 1
fi
SRC="$(cd -P "${MANUALS_DIR}" && pwd)"

# sha256 по (путь, размер, mtime) всех *.pdf + сколько секунд назад менялся самый свежий.
read -r DIGEST AGE < <(
  python3 - "${SRC}" "${SUBDIRS[@]}" <<'PY'
import hashlib
import os
import sys
import time

root, subdirs = sys.argv[1], sys.argv[2:]
digest = hashlib.sha256()
newest = 0.0
for sub in subdirs:
    for dirpath, dirnames, files in os.walk(os.path.join(root, sub)):
        dirnames.sort()
        for name in sorted(files):
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(dirpath, name)
            st = os.stat(path)
            rel = os.path.relpath(path, root)
            digest.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
            newest = max(newest, st.st_mtime)
print(digest.hexdigest(), int(time.time() - newest) if newest else -1)
PY
)

if [[ "${IF_CHANGED}" -eq 1 ]]; then
  if [[ -f "${STAMP}" && "$(cat "${STAMP}")" == "${DIGEST}" ]]; then
    exit 0
  fi
  if (( AGE >= 0 && AGE < MANUALS_SETTLE_SEC )); then
    log "PDF менялись ${AGE}s назад — жду ${MANUALS_SETTLE_SEC}s тишины"
    exit 0
  fi
fi

mkdir -p "${STATE_DIR}"
if ! mkdir "${LOCK}" 2>/dev/null; then
  log "Уже идёт синхронизация (${LOCK}) — пропуск"
  exit 0
fi
OUT="$(mktemp)"
trap 'rmdir "${LOCK}" 2>/dev/null || true; rm -f "${OUT}"' EXIT

# Runs as an `if` condition, where bash ignores `set -e` — every step needs `|| return`.
run() {
  log "rsync ${SRC} → ${SSH_HOST}:${WWW_MANUALS}"
  local remote_dirs=()
  local sub
  for sub in "${SUBDIRS[@]}"; do
    remote_dirs+=("'${WWW_MANUALS}/${sub}'")
  done
  ssh -o BatchMode=yes "${SSH_HOST}" "mkdir -p ${remote_dirs[*]}" || return
  for sub in "${SUBDIRS[@]}"; do
    [[ -d "${SRC}/${sub}" ]] || continue
    rsync -rltz --protect-args --chmod=D755,F644 --prune-empty-dirs \
      --include='*/' --include='*.pdf' --include='*.PDF' --exclude='*' \
      -e "ssh -o BatchMode=yes" \
      "${SRC}/${sub}/" "${SSH_HOST}:${WWW_MANUALS}/${sub}/" || return
  done

  local attach_flags="--skip-category"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    attach_flags+=" --dry-run"
  fi
  log "attach_manual_pdfs ${attach_flags}"
  ssh -o BatchMode=yes "${SSH_HOST}" bash -s <<EOF || return
set -euo pipefail
cd '${DEPLOY_PATH}'
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.hub.yml)
if ! "\${COMPOSE[@]}" exec -T web test -d /app/manuals-src/RU; then
  echo "ERROR: web не видит /app/manuals-src — выкатить docker-compose.prod.yml с монтированием manuals-src" >&2
  exit 3
fi
"\${COMPOSE[@]}" exec -T web python manage.py attach_manual_pdfs --dir /app/manuals-src ${attach_flags}
EOF
}

if ! run 2>&1 | tee "${OUT}"; then
  log "ERROR: синхронизация не удалась" >&2
  notify "Ошибка заливки PDF — см. ~/Library/Logs/hoocon-manual-pdfs.log"
  exit 1
fi

CHANGED="$(awk '{
  for (i = 1; i <= NF; i++) {
    if ($i ~ /^(created|updated)=[0-9]+$/) { split($i, kv, "="); n += kv[2] }
  }
} END { print n + 0 }' "${OUT}")"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "dry-run: план выше, на сайте ничего не менялось"
  exit 0
fi

echo "${DIGEST}" > "${STAMP}"
log "Готово: обновлено/создано PDF на сайте — ${CHANGED}"
if (( CHANGED > 0 )); then
  notify "На сайте обновлено PDF: ${CHANGED}"
fi
