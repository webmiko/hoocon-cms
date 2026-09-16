#!/usr/bin/env python3
"""Проверка GigaChat Authorization Key из .env (OAuth + короткий ответ).

Использование:
  cd hoocon-cms
  # добавьте в .env: GIGACHAT_CREDENTIALS=... и GIGACHAT_SCOPE=GIGACHAT_API_PERS
  python scripts/test-gigachat.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment,misc]

if load_dotenv is not None:
    load_dotenv(ROOT / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from supportchat.gigachat.client import GigachatError, chat_completion, is_configured


def main() -> int:
    if not is_configured():
        print(
            "GIGACHAT_CREDENTIALS не задан.\n"
            "Добавьте в .env в корне репозитория:\n"
            "  GIGACHAT_CREDENTIALS=ваш_authorization_key_из_studio\n"
            "  GIGACHAT_SCOPE=GIGACHAT_API_PERS",
            file=sys.stderr,
        )
        return 1
    try:
        reply = chat_completion(
            [
                {"role": "system", "content": "Отвечай одним коротким предложением."},
                {"role": "user", "content": "Привет! Ты на связи?"},
            ],
        )
    except GigachatError as exc:
        print(f"Ошибка GigaChat: {exc}", file=sys.stderr)
        return 1
    print("OK — GigaChat ответил:")
    print(reply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
