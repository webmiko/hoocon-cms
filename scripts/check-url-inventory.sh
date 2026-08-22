#!/usr/bin/env bash
# Smoke-check public URL inventory over IP / SERVER_HOST (no domain required).
# Spec: docs/seo-url-migration.md §5; ПЛАН Iter 5.
#
# Usage:
#   ./scripts/check-url-inventory.sh
#   SERVER_HOST=hoocon.ru ./scripts/check-url-inventory.sh
#   BASE_URL=http://127.0.0.1:8000 ./scripts/check-url-inventory.sh
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-hoocon.ru}"
BASE_URL="${BASE_URL:-https://${SERVER_HOST}}"
HOST_HEADER="${HOST_HEADER:-hoocon.ru}"

# path|expected_status (comma-separated OK codes)
PATHS=(
  "/|200"
  "/catalog|200"
  "/api/health/|200"
  "/company|200"
  "/zavod|200"
  "/gde-kupit|200"
  "/statyi|200"
  "/novosti|200"
  "/compare|200"
  "/consultation|200"
  "/oferta|200"
  "/privacy-policy|200"
  "/terms|200"
  "/robots.txt|200"
  "/sitemap.xml|200"
  "/llms.txt|200"
  "/privod-protivipozharniy-3nm|301,302"
  "/privod-vozdushniy-hvd-5nm|301,302"
  "/tproduct/629593806372-bv215-sharovoi-kran-2-hodovii-dn-15|301,302"
  "/catalog/tproduct/437694431492-bv240-sharovoi-kran-2-hodovii-dn-40|301,302"
  "/statyi/tpost/ispolnitelnoe-oborudovanie-ovk|301,302"
  "/sale|301,302"
  "/sitemap|301,302"
  "/elektroprivody-dlya-zaslonok-ventilyatsii|301,302"
  "/news/mirklimata_2025|301,302"
  "/catalog/|301,302"
  "/index.html|301,302"
)
pass=0
fail=0

echo "==> URL inventory against ${BASE_URL} (Host: ${HOST_HEADER})"

for entry in "${PATHS[@]}"; do
  path="${entry%%|*}"
  expect="${entry##*|}"
  # shellcheck disable=SC2086
  code="$(curl -sS -o /dev/null -w '%{http_code}' \
    --max-time 15 \
    -H "Host: ${HOST_HEADER}" \
    "${BASE_URL}${path}" || echo "000")"
  ok=0
  IFS=',' read -r -a allowed <<< "${expect}"
  for a in "${allowed[@]}"; do
    if [[ "${code}" == "${a}" ]]; then
      ok=1
      break
    fi
  done
  if [[ "${ok}" -eq 1 ]]; then
    echo "OK  ${code}  ${path}"
    pass=$((pass + 1))
  else
    echo "FAIL ${code} (want ${expect})  ${path}" >&2
    fail=$((fail + 1))
  fi
done

echo "==> pass=${pass} fail=${fail}"
if [[ "${fail}" -gt 0 ]]; then
  exit 1
fi
