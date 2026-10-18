---
name: local-dev
description: Запуск/остановка локальных dev-серверов hoocon-cms (backend 8002, frontend 5174). Вызывать при «запусти локалку», «останови локалку», «подними dev».
---

# Start / Stop local dev servers

Прочитай и применяй канон: `.cursor/rules/stop-local-dev.mdc`.

Ключевое:

- Пины портов: backend `8002`, frontend `5174` (Vite проксирует `/api`
  на `127.0.0.1:8002`). Порты 8000/5173 не занимать — они для других
  проектов.
- «запусти локалку» → `./scripts/start-local-dev.sh`;
  «останови локалку» → `./scripts/stop-local-dev.sh` (только dev-серверы).
- Postgres/данные не останавливать и не сбрасывать без явной просьбы.
