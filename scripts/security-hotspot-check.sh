#!/usr/bin/env bash
# Security hotspot checks for Hoocon CMS (no cart/paywall).
# Exit 0 = ok, 1 = violations.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"
cd "$ROOT"

FAIL=0
fail() { echo "✗ $1"; FAIL=$((FAIL + 1)); }
ok() { echo "✓ $1"; }

# 1) Frontend: no dangerouslySetInnerHTML without sanitization
if [ -d "$ROOT/frontend/src" ]; then
  if grep -RInE 'dangerouslySetInnerHTML' frontend/src 2>/dev/null | grep -v node_modules; then
    fail "frontend: dangerouslySetInnerHTML — нужна санитизация (security-baseline)"
  else
    ok "frontend: нет dangerouslySetInnerHTML"
  fi
fi

# 2) Hardcoded live Stripe/YooKassa keys (should never appear in v1)
if grep -RInE 'sk_live_[A-Za-z0-9]+|live_YOOKASSA|STRIPE_SECRET_KEY\s*=\s*["\x27]sk_' \
  backend frontend --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' \
  2>/dev/null | grep -v node_modules | grep -v '.venv'; then
  fail "Найдены платёжные секреты в коде"
else
  ok "Нет платёжных секретов в коде"
fi

# 3) CORS * with credentials anti-pattern in settings
if [ -f "$ROOT/backend/config/settings.py" ]; then
  if grep -nE 'CORS_ALLOW_ALL_ORIGINS\s*=\s*True' backend/config/settings.py 2>/dev/null; then
    fail "CORS_ALLOW_ALL_ORIGINS=True запрещён"
  else
    ok "CORS не открыт на *"
  fi

  # 4) DEBUG True hardcoded without getenv (bad for prod copy-paste)
  if grep -nE '^DEBUG\s*=\s*True\s*$' backend/config/settings.py 2>/dev/null; then
    fail "DEBUG=True захардкожен — только через env"
  else
    ok "DEBUG из env"
  fi
fi

# 2) .env must not be tracked
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  fail ".env отслеживается git — убрать из индекса"
else
  ok ".env не в git index"
fi

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
