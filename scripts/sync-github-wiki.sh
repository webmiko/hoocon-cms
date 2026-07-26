#!/usr/bin/env bash
# Пересобирает wiki-индекс docs/README.md из docs/*.md.
# GitHub Wiki на private Free недоступен — канон wiki = docs/ в репозитории.
# При Pro/Team: ./scripts/sync-github-wiki.sh --push (отдельный remote *.wiki.git).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="${ROOT}/docs"
INDEX="${DOCS}/README.md"

EXCLUDE=(
  "README.md"
  "kb-update-proposals.md"
)

is_excluded() {
  local name="$1"
  local ex
  for ex in "${EXCLUDE[@]}"; do
    [[ "$name" == "$ex" ]] && return 0
  done
  return 1
}

pages=()
while IFS= read -r -d '' src; do
  base="$(basename "$src")"
  if is_excluded "$base"; then
    continue
  fi
  pages+=("$base")
done < <(find "${DOCS}" -maxdepth 1 -type f -name '*.md' -print0 | sort -z)

tmp="$(mktemp)"
{
  cat <<'EOF'
# Документация Hoocon CMS

Индекс проектной документации (wiki в репозитории).
Исходники — этот каталог `docs/`.

**Без онлайн-корзины и оплаты в v1** — RFQ вместо checkout.

Пересборка оглавления: `./scripts/sync-github-wiki.sh`.

## Оглавление

EOF
  for base in "${pages[@]}"; do
    h1="$(grep -m1 -E '^# ' "${DOCS}/${base}" | sed 's/^# //' || true)"
    label="${h1:-${base%.md}}"
    echo "- [${label}](${base})"
  done
} >"${tmp}"

mv "${tmp}" "${INDEX}"
echo "Updated ${INDEX} (${#pages[@]} pages)."
