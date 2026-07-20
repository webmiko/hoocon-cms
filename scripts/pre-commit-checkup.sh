#!/usr/bin/env bash
# Pre-commit checkup — обязательная проверка перед коммитом (Hoocon CMS).
# Backend: ruff, format, mypy, pytest, pip-audit, секреты, длина строк, hotspots.
# Выход: 0 — чисто, 1 — есть проблемы.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

ok() { echo -e "${GREEN}✓ $1${NC}"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}✗ $1${NC}"; FAIL=$((FAIL + 1)); }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }

BACKEND="$ROOT/backend"
# Postgres — рабочая БД проекта (docs/infra-reg.py.md). Локально поднимается
# через docker compose up -d или Homebrew postgresql@18. SQLite — только fallback
# при отсутствии Postgres (явно USE_SQLITE=True).
export USE_SQLITE="${USE_SQLITE:-False}"

echo "══════════════════════════════════════════════════"
echo "  Pre-commit checkup (hoocon-cms)"
echo "══════════════════════════════════════════════════"
echo ""

if [ ! -f "$BACKEND/pyproject.toml" ]; then
  fail "backend/pyproject.toml не найден"
  echo "Результат: $FAIL failed"
  exit 1
fi

# ── 1. Ruff check ────────────────────────────────────────────
if (cd "$BACKEND" && poetry run ruff check .) >/dev/null 2>&1; then
  ok "ruff check — чисто"
else
  fail "ruff check — ошибки (cd backend && poetry run ruff check .)"
fi

# ── 2. Ruff format ───────────────────────────────────────────
if (cd "$BACKEND" && poetry run ruff format --check .) >/dev/null 2>&1; then
  ok "ruff format — чисто"
else
  fail "ruff format — нужен формат (cd backend && poetry run ruff format .)"
fi

# ── 3. mypy ──────────────────────────────────────────────────
if (cd "$BACKEND" && poetry run mypy config leads crm catalog content manage.py) >/dev/null 2>&1; then
  ok "mypy — чисто"
else
  fail "mypy — ошибки типов (cd backend && poetry run mypy config leads crm catalog content manage.py)"
fi

# ── 4. pytest (exit 5 = нет тестов — допустимо на каркасе) ───
set +e
(cd "$BACKEND" && poetry run pytest -q)
PYTEST_CODE=$?
set -e
if [ "$PYTEST_CODE" -eq 0 ]; then
  ok "pytest — тесты прошли"
elif [ "$PYTEST_CODE" -eq 5 ]; then
  warn "pytest — тестов пока нет (exit 5); после catalog — обязательны"
  ok "pytest — каркас без тестов принят"
else
  fail "pytest — ошибки (cd backend && poetry run pytest -q)"
fi

# ── 5. pip-audit ─────────────────────────────────────────────
if (cd "$BACKEND" && poetry run pip-audit --strict) >/dev/null 2>&1; then
  ok "pip-audit — нет уязвимостей"
else
  fail "pip-audit — есть уязвимости (cd backend && poetry run pip-audit --strict)"
fi

# ── 6. Diff / staging ────────────────────────────────────────
STAGED=$(git diff --cached --name-only 2>/dev/null || true)
if [ -z "$STAGED" ]; then
  STAGED=$(git diff --name-only 2>/dev/null || true)
fi

PY_FILES=""
if [ -n "$STAGED" ]; then
  FORBIDDEN=$(echo "$STAGED" | grep -E '(^|/)\.env$|(^|/)\.env\.[^/]+$|db\.sqlite3$|\.sqlite3$|(^|/)media/|(^|/)\.venv/' || true)
  FORBIDDEN=$(echo "$FORBIDDEN" | grep -vE '\.env\.example$|\.env\.template$' || true)
  if [ -z "$FORBIDDEN" ]; then
    ok "Нет запрещённых файлов в diff"
  else
    fail "Запрещённые файлы в diff: $FORBIDDEN"
  fi

  PY_FILES=$(echo "$STAGED" | grep -E '\.py$' || true)
  if [ -n "$PY_FILES" ]; then
    # shellcheck disable=SC2086
    # Ignore fixture markers like password="test-pass-not-secret" in tests.
    SECRETS=$(
      echo "$PY_FILES" | xargs grep -nE \
        '(sk_live_|sk_test_|SECRET_KEY\s*=\s*["\x27][^"\x27]{16,}|password\s*=\s*["\x27][^"\x27]{8,}|EMAIL_HOST_PASSWORD\s*=\s*["\x27][^"\x27]+)' \
        2>/dev/null \
        | grep -vE 'not-secret|change-me|ci-secret|ci-db-password|password12' \
        | cut -d: -f1 \
        | sort -u \
        || true
    )
    if [ -z "$SECRETS" ]; then
      ok "Нет хардкоженных секретов в .py"
    else
      fail "Возможные секреты в: $SECRETS"
    fi
  fi
else
  ok "Нет изменений для проверки файлов"
fi

# ── 7. Строки > 119 в добавленных .py ────────────────────────
if [ -n "$PY_FILES" ]; then
  LONG_LINES=""
  for f in $PY_FILES; do
    if [ -f "$f" ]; then
      ADDED_LONG=$(
        git diff --unified=0 -- "$f" 2>/dev/null | (cd "$BACKEND" && poetry run python -c '
import sys
path = sys.argv[1]
out = []
for raw in sys.stdin:
    if not raw.startswith("+") or raw.startswith("+++"):
        continue
    text = raw[1:].rstrip("\n")
    if len(text) > 119:
        out.append(f"{path}: {len(text)} chars")
if out:
    print("\n".join(out))
' "$f") || true
      )
      if [ -n "$ADDED_LONG" ]; then
        LONG_LINES="${LONG_LINES}${ADDED_LONG}"$'\n'
      fi
    fi
  done
  if [ -z "$LONG_LINES" ]; then
    ok "Добавленные строки ≤ 119 символов"
  else
    fail "Добавленные строки > 119 символов:"$'\n'"$LONG_LINES"
  fi
fi

# ── 8. print() вне tests/ ────────────────────────────────────
if [ -n "$PY_FILES" ]; then
  NON_TEST_PY=$(echo "$PY_FILES" | grep -vE '(^|/)tests/' || true)
  if [ -n "$NON_TEST_PY" ]; then
    # shellcheck disable=SC2086
    PRINTS=$(echo "$NON_TEST_PY" | xargs grep -lE '^\s*print\(' 2>/dev/null | grep -v '__pycache__' || true)
    if [ -z "$PRINTS" ]; then
      ok "Нет print() вне tests/"
    else
      fail "print() найден (используй logger): $PRINTS"
    fi
  fi
fi

# ── 9. .env не в staging ─────────────────────────────────────
if git diff --cached --name-only 2>/dev/null | grep -qxE '\.env' 2>/dev/null; then
  fail ".env в staging — НЕ коммить"
else
  ok ".env не в staging"
fi

# ── 10. Security hotspots (Hoocon) ───────────────────────────
if [ -x "$ROOT/scripts/security-hotspot-check.sh" ]; then
  set +e
  HOTSPOT_OUT=$("$ROOT/scripts/security-hotspot-check.sh" 2>&1)
  HOTSPOT_OK=$?
  set -e
  if [ "$HOTSPOT_OK" -eq 0 ]; then
    ok "Security hotspots — RFQ/PII/цены/CSP"
  else
    fail "Security hotspots:"$'\n'"$HOTSPOT_OUT"
  fi
else
  warn "scripts/security-hotspot-check.sh отсутствует или не executable"
fi

# ── 11. Frontend lint (если менялся frontend/) ───────────────
FE_CHANGED=$(echo "$STAGED" | grep -E '^frontend/' || true)
if [ -n "$FE_CHANGED" ] && [ -f "$ROOT/frontend/package.json" ]; then
  if (cd "$ROOT/frontend" && npm run lint) >/dev/null 2>&1; then
    ok "frontend lint — чисто"
  else
    fail "frontend lint — ошибки (cd frontend && npm run lint)"
  fi
fi

# ── Итог ─────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════"
echo -e "  Результат: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "══════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
