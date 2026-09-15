# Чеклист после деплоя (hoocon.ru)

Краткий список после merge в `main` / ручного `deploy-to-vps.sh`.
Sentry недоступен в РФ — ops-алерты через Telegram + логи.

## 1. CI / образ

- [ ] GitHub Actions `check` зелёный (pytest, vitest, e2e smoke)
- [ ] `build` опубликовал образ на GHCR
- [ ] `deploy` завершился без ошибок (если пуш в `main`)

## 2. На VPS сразу после выката

```bash
cd /opt/hoocon   # или ваш DEPLOY_PATH
docker compose ps
docker compose logs --tail=80 web celery
curl -fsS http://127.0.0.1:8000/api/health/
curl -fsS --http1.1 http://127.0.0.1/ | grep -q '<div id="root">'
```

- [ ] `web` и `celery` в статусе `running`, healthcheck healthy
- [ ] `/api/health/` → JSON с `ok`
- [ ] GET `/` через nginx → SPA shell (`<div id="root">`)

## 3. Миграции и статика

При смене моделей (обычно в deploy-remote уже есть):

```bash
docker compose exec web python manage.py migrate --noinput
```

- [ ] Миграции применены без ошибок

## 4. Smoke в браузере

- [ ] `/` — главная, подбор
- [ ] `/catalog` — каталог
- [ ] `/catalog/…/…` — карточка SKU
- [ ] `/rfq` — форма КП
- [ ] `/admin/` — вход (OTP / passkey)

## 5. Ops: мониторинг и алерты

В `.env` на VPS (если ещё не задано):

```bash
# Chat ID из лички с ботом (/chatid в @HooconMsk_bot)
OPS_TELEGRAM_CHAT_IDS=123456789
TELEGRAM_BOT_TOKEN=…
OPS_ALERT_DEDUP_SECONDS=900
```

- [ ] Cron: `/etc/cron.d/hoocon` (`vps-install-cron.sh`)
- [ ] Logrotate: `/etc/logrotate.d/hoocon-logs` (`vps-install-logrotate.sh`)
- [ ] `monitor-health.sh` в cron каждые 5 мин → `/var/log/hoocon-monitor.log`
- [ ] Тест алерта (опционально):
  `docker compose exec web python manage.py ops_telegram_alert --message "post-deploy ok" --dedup-key manual`

## 6. Docker-логи

В `docker-compose.prod.yml` уже задано: `max-size: 10m`, `max-file: 3` на сервисах.

## 7. Бэкапы

- [ ] `backup-vps.sh` в cron 03:00 UTC
- [ ] После крупных миграций — ручной `./scripts/backup-vps.sh` до выката

## 8. Non-root (web/celery uid 1000)

Если после выката 500 на upload/media:

```bash
sudo chown -R 1000:1000 /var/www/hoocon/media
```

---

См. также: [backups-restore.md](backups-restore.md)
