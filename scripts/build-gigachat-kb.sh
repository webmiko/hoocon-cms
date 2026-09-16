#!/usr/bin/env bash
# Собрать gigachat_kb.txt из локальных _manuals-ru и _инструкции-pdf.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
poetry run python manage.py build_gigachat_kb
