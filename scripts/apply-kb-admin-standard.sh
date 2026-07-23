#!/usr/bin/env bash
# Копирует патч стандарта Admin в канон БЗ (локально, где симлинк живой).
# Usage: ./scripts/apply-kb-admin-standard.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
PATCH="$ROOT/docs/kb-patch-django-admin-standard"
KB_LINK="$ROOT/_Универсальная-база-знаний"
SRC="$PATCH/02-Примеры-кода/django-admin-стандарт"

if [[ ! -d "$SRC" ]]; then
  echo "Нет патча: $SRC" >&2
  exit 1
fi

if [[ ! -e "$KB_LINK" ]]; then
  echo "Нет симлинка БЗ: $KB_LINK" >&2
  exit 1
fi

if [[ ! -d "$KB_LINK" ]]; then
  echo "Симлинк БЗ битый (цель недоступна): $KB_LINK" >&2
  echo "Откройте канон на машине с /Users/niko/GitHub/Универсальная-база-знаний" >&2
  exit 1
fi

DEST="$KB_LINK/02-Примеры-кода/django-admin-стандарт"
mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"

echo "Скопировано → $DEST"
echo "Дальше вручную: влить patches/*.snippet в AGENTS.md, веб-стек README, ИЗМЕНЕНИЯ.md"
echo "См. $PATCH/APPLY.md"
