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
8. **CI/CD** — единственный путь деплоя: GitHub Actions на push в
   `develop` / `main` (не с локалки). Pipeline: test → lint → build
   (образ в **GHCR** + `frontend/dist`) → deploy SSH
   (`scripts/deploy-remote.sh`). Секреты репо: `SSH_PRIVATE_KEY`,
   `SSH_USER`, `SERVER_HOST`, `DEPLOY_PATH`. `.env` на VPS не
   перезаписывается CI. Локальный `scripts/deploy-to-vps.sh` — stub
   (exit 1). Одноразовый перенос БД: `scripts/sync-db-to-vps.sh`.

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
- [ ] **SEO:** инвентарь URL 200/301
      ([seo-url-migration.md](seo-url-migration.md) §5)
- [ ] Метрика / Вебмастер на новом origin
- [ ] Smoke: `/`, `/catalog`, SKU, форма RFQ, `/api/health/`
- [ ] Бэкап до и после миграции

---

## 5. Риски

| Риск | Митигация |
|------|-----------|
| Малый VPS / OOM | лимиты workers, swap осторожно, мониторинг |
| Доставляемость почты | SPF/DKIM, не слать с «голого» IP без PTR |
| Downtime cutover | параллельный прогон, низкий TTL, rollback DNS |
| DDoS-Guard у Tilda сейчас | на VPS — fail2ban / лимиты nginx, при необходимости защита reg.ru |

Связано: [market-analysis.md](market-analysis.md), план проекта (scope / infra).
