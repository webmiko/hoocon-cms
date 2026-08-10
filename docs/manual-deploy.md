# Ручной деплой (когда Actions исчерпан)

Запасной путь без минут GitHub Actions. Тот же смысл, что CI
(test/lint → build → SSH), но с ноутбука.

**Основной путь** по-прежнему: `git push` → Actions → VPS
([infra-reg-ru.md](infra-reg-ru.md)). Ручной — только если квота
2000 мин/мес кончилась или CI заблокирован биллингом
([actions-minutes.md](actions-minutes.md)).

## Команда

```bash
./scripts/deploy-to-vps.sh
```

Полный цикл:

1. `./scripts/pre-commit-checkup.sh` (тесты, ruff, mypy, pip-audit, secrets…)
2. `frontend`: `npm ci && npm run build`
3. Docker-образ **`linux/amd64`** (`backend/`, тег `ghcr.io/<owner>/hoocon-cms:<sha>`)
4. Доставка образа: `docker save | ssh … docker load` (по умолчанию)
5. `scripts/deploy-remote.sh` — compose, `frontend/dist`, nginx, health
6. Smoke: `http://<VPS>/api/health/`

## Флаги

| Флаг | Зачем |
|------|--------|
| `--checks-only` | Только checkup, без выкладки |
| `--skip-checks` | Аварийно без checkup (не для обычной работы) |
| `--skip-frontend` | Уже есть свежий `frontend/dist` |
| `--push-ghcr` | Push в GHCR + pull на VPS (нужен `write:packages`) |
| `--dry-run` | План без сборки/отправки |
| `-h` | Справка |

## SSH и пути

По умолчанию:

- `SSH_HOST=hoocon-prod` (Host в `~/.ssh/config`)
- `DEPLOY_PATH=/opt/hoocon`
- фронт: `/var/www/hoocon/frontend/dist`

Опционально скопировать `scripts/deploy.env.example` → `.local/deploy.env`:

```bash
SSH_HOST=hoocon-prod
DEPLOY_PATH=/opt/hoocon
# SMOKE_HOST=161.104.19.49   # если нужен явный IP для smoke
```

## Важно: архитектура образа

VPS — **amd64**. С Apple Silicon без `--platform linux/amd64`
контейнер не стартует. Скрипт всегда собирает под `linux/amd64`
и проверяет `Os/Architecture` после build.

## GHCR vs docker load

| Способ | Когда |
|--------|--------|
| `docker load` (default) | Нет прав на push в GHCR / экономия шагов |
| `--push-ghcr` | Есть `write:packages`, VPS тянет образ сам |

CI по-прежнему пушит в GHCR и вызывает `deploy-remote.sh` с
`IMAGE_TRANSFER=pull`.

## Чеклист перед ручным деплоем

- [ ] `./scripts/actions-minutes.py` — минут действительно нет / CI красный
- [ ] Ветка с нужным кодом (обычно `develop`), dirty tree осознан
- [ ] SSH: `ssh hoocon-prod 'echo ok'`
- [ ] На сервере есть `/opt/hoocon/.env` (скрипт его **не** перезаписывает)
- [ ] После выкладки: `/api/health/`, главная, каталог, RFQ

Откат: на VPS выставить предыдущий `DOCKER_IMAGE=…` в `.env` и
`docker compose -f docker-compose.yml -f docker-compose.hub.yml up -d`.
