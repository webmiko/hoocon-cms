#!/usr/bin/env bash
# macOS launchd-агент: сам заливает изменённые PDF мануалов/паспортов на прод.
#
# Срабатывает при изменениях в RU/, EN/, «паспорт изделия»/ (WatchPaths) и
# раз в INTERVAL секунд; дальше scripts/sync-manual-pdfs.sh --if-changed
# сам решает, есть ли что заливать.
#
# Usage:
#   ./scripts/install-manual-pdfs-watcher.sh              # установить / обновить
#   ./scripts/install-manual-pdfs-watcher.sh --status     # состояние + хвост лога
#   ./scripts/install-manual-pdfs-watcher.sh --uninstall  # снять
#
# Env: INTERVAL=300, MANUALS_DIR=<repo>/_инструкции-pdf
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="ru.hoocon.manual-pdfs-sync"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG="${HOME}/Library/Logs/hoocon-manual-pdfs.log"
INTERVAL="${INTERVAL:-300}"
MANUALS_DIR="${MANUALS_DIR:-${ROOT}/_инструкции-pdf}"
DOMAIN="gui/$(id -u)"

xml_escape() {
  local s="$1"
  s="${s//&/&amp;}"
  s="${s//</&lt;}"
  s="${s//>/&gt;}"
  printf '%s' "${s}"
}

case "${1:-}" in
  --uninstall)
    launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
    rm -f "${PLIST}"
    echo "Снято: ${LABEL}"
    exit 0
    ;;
  --status)
    launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null \
      | grep -E '^\s*(state|last exit code|runs) =' || echo "Не установлен: ${LABEL}"
    [[ -f "${LOG}" ]] && tail -n 20 "${LOG}"
    exit 0
    ;;
  "") ;;
  *) echo "Unknown flag: $1" >&2; exit 2 ;;
esac

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Только macOS (launchd)" >&2
  exit 1
fi
if [[ ! -d "${MANUALS_DIR}" ]]; then
  echo "Нет каталога ${MANUALS_DIR}" >&2
  exit 1
fi
SRC="$(cd -P "${MANUALS_DIR}" && pwd)"

watch_paths=""
for sub in "RU" "EN" "паспорт изделия"; do
  [[ -d "${SRC}/${sub}" ]] || continue
  watch_paths+="    <string>$(xml_escape "${SRC}/${sub}")</string>
"
done

mkdir -p "$(dirname "${PLIST}")" "$(dirname "${LOG}")"
cat > "${PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$(xml_escape "${ROOT}/scripts/sync-manual-pdfs.sh")</string>
    <string>--if-changed</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>MANUALS_DIR</key>
    <string>$(xml_escape "${SRC}")</string>
  </dict>
  <key>WatchPaths</key>
  <array>
${watch_paths}  </array>
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>$(xml_escape "${LOG}")</string>
  <key>StandardErrorPath</key>
  <string>$(xml_escape "${LOG}")</string>
</dict>
</plist>
PLIST

plutil -lint "${PLIST}" >/dev/null
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "${DOMAIN}" "${PLIST}"
echo "Установлено: ${LABEL} (каждые ${INTERVAL}s + при изменениях в ${SRC})"
echo "Лог: ${LOG}"
