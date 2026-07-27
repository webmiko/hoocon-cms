# Инфраструктура prod: VPS / домен / почта reg.ru

Дата: 2026-07-19  
Статус: **зафиксировано** для разработки и деплоя.

---

## 1. Решение

Готовый проект работает **на одной платформе reg.ru**:

| Компонент | Где |
|-----------|-----|
| Хостинг приложения | VPS reg.ru (Docker Compose: web, db, redis, worker) |
| Домен `hoocon.ru` (и зоны) | DNS / управление доменом в reg.ru |
| Корпоративная почта | Почтовый сервис / ящики reg.ru (`sales@`, `info@`, …) |
| TLS | HTTPS на VPS (Let's Encrypt через nginx **или** сертификат reg.ru) |

Внешние SaaS для почты (SendGrid и т.п.) **не планируем** как основу:
письма заявок и уведомления — через SMTP ящиков на reg.ru.

Референс паттернов из БЗ: `lms-backend` (nginx + Compose + Celery +
деплой по SSH), адаптировать под лимиты одного VPS.

---

## 2. Следствия для архитектуры (учитывать с итерации 0–5)

1. **Один хост** — Postgres, Redis, Django/gunicorn, Celery worker,
   nginx, статика фронта. Не рассчитывать на отдельный managed DB
   в v1 (если позже — осознанное исключение).
2. **Ресурсы VPS** — Postgres FTS в v1 вместо Meilisearch; без тяжёлых
   sidecar без нужды; лимиты Docker (логи json-file, prune).
3. **SMTP** — настройки в `.env` (`EMAIL_HOST`, порт, TLS, user/password
   ящика reg.ru); Celery шлёт Lead-уведомления; в тестах — eager + mock.
4. **DNS** — A/AAAA на VPS; MX/SPF/DKIM/DMARC для домена на почте
   reg.ru (чеклист перед cutover с Tilda).
5. **Почта ≠ контейнер обязателен** — предпочтительно штатная почта
   reg.ru; самописный Postfix в Docker только если явно решим иначе.
6. **Бэкапы** — дамп Postgres + media на диск VPS / объектное хранилище
   reg.ru по расписанию (скрипт + cron на хосте).
7. **Секреты** — только `.env` на сервере; в git — `.env.example`.
8. **CI/CD** — основной путь: GitHub Actions на push в `develop` /
   `main`. Pipeline: test → lint → build (образ в **GHCR** +
   `frontend/dist`) → deploy SSH (`scripts/deploy-remote.sh`).
   Секреты репо: `SSH_PRIVATE_KEY`, `SSH_USER`, `SERVER_HOST`,
   `DEPLOY_PATH`. `.env` на VPS не перезаписывается. **Запасной путь**
   при исчерпании минут Actions: `./scripts/deploy-to-vps.sh`
   ([manual-deploy.md](manual-deploy.md)) — checkup + amd64 image +
   `docker load` + тот же `deploy-remote.sh`. Одноразовый перенос БД:
   `scripts/sync-db-to-vps.sh`. Квота Free private: **2000 мин/мес** →
   `./scripts/actions-minutes.py` ([actions-minutes.md](actions-minutes.md)).

---

## 3. Compose на VPS

```
host nginx (:80/:443) → 127.0.0.1:8000 (gunicorn)
                      → /var/www/hoocon/{frontend/dist,media,staticfiles}
Compose: db, redis, web, celery_worker
Образ web/celery: GHCR (ghcr.io/<owner>/hoocon-cms:<sha>)
  docker-compose.yml + docker-compose.hub.yml
```

Локально: `docker-compose.yml` (только db + redis). Prod-файлы:
`docker-compose.prod.yml` (копируется на сервер как `docker-compose.yml`),
`docker-compose.hub.yml`.

---

## 4. Чеклист cutover (когда MVP готов)

- [ ] DNS A → новый VPS; TTL снижен заранее
- [ ] TLS валиден; HSTS после стабилизации
- [ ] MX/SPF/DKIM; тест письма Lead → `sales@hoocon.ru`
- [x] **SEO:** инвентарь URL 200/301 **по IP**
      ([seo-url-migration.md](seo-url-migration.md) §5;
      `scripts/check-url-inventory.sh`) — полный после DNS
- [ ] Метрика / Вебмастер на новом origin
- [ ] Smoke: `/`, `/catalog`, SKU, форма RFQ, `/api/health/`
- [x] Бэкап скрипт + cron на VPS (`scripts/backup-vps.sh`)

---

## 5. Риски

| Риск | Митигация |
|------|-----------|
| Малый VPS / OOM | лимиты workers, swap осторожно, мониторинг |
| Доставляемость почты | SPF/DKIM, не слать с «голого» IP без PTR |
| Downtime cutover | параллельный прогон, низкий TTL, rollback DNS |
| DDoS-Guard у Tilda сейчас | на VPS — fail2ban / лимиты nginx, при необходимости защита reg.ru |

---

## 6. Бэкапы (Postgres + media)

Скрипт на хосте: [`scripts/backup-vps.sh`](../scripts/backup-vps.sh).

| Параметр | Значение по умолчанию |
|----------|------------------------|
| Каталог | `/opt/hoocon/backups/<UTC-stamp>/` |
| DB | `pg_dump -Fc` из контейнера `db` → `hoocon.dump` |
| Media | `tar.gz` из `/var/www/hoocon/media` → `media.tar.gz` |
| Retention | 7 дней (`RETENTION_DAYS`) |

Прогон вручную:

```bash
ssh hoocon-prod 'sudo /opt/hoocon/scripts/backup-vps.sh'
```

После деплоя скопировать скрипт на VPS (если ещё нет в `/opt/hoocon/scripts/`):

```bash
scp scripts/backup-vps.sh hoocon-prod:/tmp/
ssh hoocon-prod 'sudo cp /tmp/backup-vps.sh /opt/hoocon/scripts/ && sudo chmod +x /opt/hoocon/scripts/backup-vps.sh'
```

Crontab (раз в сутки, 03:15 UTC):

```cron
15 3 * * * /opt/hoocon/scripts/backup-vps.sh >> /var/log/hoocon-backup.log 2>&1
```

### Restore (кратко)

```bash
# DB
cd /opt/hoocon
BACKUP=/opt/hoocon/backups/<stamp>
docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" \
  --clean --if-exists --no-owner --no-acl /tmp/hoocon.dump
# (сначала: docker cp $BACKUP/hoocon.dump $(docker compose ps -q db):/tmp/hoocon.dump)

# Media
sudo tar -C /var/www/hoocon -xzf "$BACKUP/media.tar.gz"
```

---

## 7. Мониторинг (минимум до Sentry)

Скрипт: [`scripts/monitor-health.sh`](../scripts/monitor-health.sh) —
`curl` `/api/health/` + порог заполнения диска (`DISK_WARN_PCT=85`).

```cron
*/5 * * * * HEALTH_URL=http://127.0.0.1:8000/api/health/ \
  /opt/hoocon/scripts/monitor-health.sh
```

Лог: `/var/log/hoocon-monitor.log`. Ненулевой exit → mail от cron (если
настроен). Sentry — после стабилизации (Iter 6).

---

## 8. Отложено до домена / SMTP

Пока нет cutover DNS `hoocon.ru` и почты reg.ru **не** делать в коде/проде:

- TLS Let’s Encrypt, HSTS «в бою», HTTP→HTTPS redirect
- SMTP smoke Lead/CRM, SPF/DKIM
- Client auth / ЛК / чат поддержки
- **AnalogMap / `/analog-belimo`** — только после валидированной карты
  ([data-quality-etl.md](data-quality-etl.md)); сейчас лишь
  `SKU.analog_belimo_code` + ETL heuristics

Связано: [market-analysis.md](market-analysis.md), план проекта (scope / infra).
