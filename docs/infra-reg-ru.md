# Инфраструктура prod: VPS / домен (reg.ru) + почта (Яндекс 360)

Дата: 2026-07-28  
Статус: **зафиксировано** для разработки и деплоя.

---

## 1. Решение

| Компонент | Где | Горизонт |
|-----------|-----|----------|
| Хостинг приложения | VPS reg.ru (Docker Compose: web, db, redis, worker) | постоянный |
| Домен `hoocon.ru` + зона DNS | reg.ru (NS регистратора) | постоянный |
| Корпоративная почта | **Яндекс 360** (`sales@` отдел + сервисный `noreply@`) | **~1 год** (далее — пересмотр) |
| TLS сайта | Let's Encrypt на VPS (nginx) **или** сертификат reg.ru | постоянный |
| Исходящий SMTP приложения | `smtp.yandex.ru` (**ящик `noreply@`**, не общий `sales@`) | пока почта на 360 |

**Не** держим почту на reg.ru и **не** поднимаем Postfix в Docker в v1.
Внешний ESP (SendGrid и т.п.) — не основа: Lead / CRM / OTP идут через
SMTP ящика Яндекс 360.

**DNS не делегируем целиком на Яндекс:** зона остаётся в reg.ru, чтобы
A/AAAA сайта указывали на VPS, а MX/TXT почты — на Яндекс (ручные записи).
Полная делегация NS на Яндекс ломает простой контроль web-DNS на VPS.

Референс паттернов: `lms-backend` (nginx + Compose + Celery + деплой
по SSH), адаптировать под лимиты одного VPS.

Официальные доки Яндекс 360 (актуальные значения сверять там):

- [Подключение домена](https://yandex.ru/support/yandex-360/business/admin/ru/migration/add-domain)
- [DNS для почты](https://yandex.ru/support/yandex-360/business/admin/ru/mail/start)
- [Почтовые клиенты / SMTP](https://yandex.ru/support/yandex-360/business/mail/ru/mail-clients/others)

---

## 2. Следствия для архитектуры (итерации 0–5)

1. **Один хост** — Postgres, Redis, Django/gunicorn, Celery worker,
   nginx, статика фронта. Managed DB в v1 не планируем.
2. **Ресурсы VPS** — Postgres FTS в v1; без тяжёлых sidecar; лимиты
   Docker (логи json-file, prune).
3. **SMTP** — в `.env` на VPS: `EMAIL_HOST=smtp.yandex.ru`, порт **465**,
   `EMAIL_USE_SSL=True`, логин = **сервисный** ящик `noreply@hoocon.ru`
   (обычный аккаунт 360 с паролем приложения; **не** общий ящик отдела
   `sales@` — у общего нет своего Яндекс ID). Celery шлёт Lead / CRM;
   в тестах — eager + mock.
4. **DNS** — сейчас зона на Tilda (§4); к cutover — NS/зона на reg.ru,
   A → VPS; MX/SPF/DKIM Яндекса **уже есть** (не ломать).
5. **Почта ≠ контейнер** — только Яндекс 360; Postfix в Docker только
   если явно решим иначе.
6. **Бэкапы** — дамп Postgres + media на диск VPS / объектное хранилище
   reg.ru (скрипт + cron на хосте). Почта бэкапится средствами 360 /
   политикой организации — не в Docker.
7. **Секреты** — только `.env` на сервере; в git — `.env.example`.
8. **CI/CD** — GitHub Actions на push в `develop` / `main`: test →
   lint → build (GHCR + `frontend/dist`) → deploy SSH
   (`scripts/deploy-remote.sh`). Секреты репо: `SSH_PRIVATE_KEY`,
   `SSH_USER`, `SERVER_HOST`, `DEPLOY_PATH`. `.env` на VPS не
   перезаписывается. Запасной путь: `./scripts/deploy-to-vps.sh`
   ([manual-deploy.md](manual-deploy.md)). Одноразовый перенос БД:
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
`docker-compose.prod.yml` (на сервере как `docker-compose.yml`),
`docker-compose.hub.yml`.

---

## 4. Текущая зона DNS (снимок с Tilda, 2026-07-28)

Сейчас DNS ведётся в **панели Tilda** (не в зоне reg.ru напрямую).
Снимок записей — база для cutover; почта Яндекс **уже** настроена.

| Хост | Тип | Значение | Действие при cutover |
|------|-----|----------|----------------------|
| `hoocon.ru` | A | `176.57.64.46` (Tilda / DDoS-Guard) | **Заменить** на IPv4 VPS |
| `www.hoocon.ru` | CNAME | `hoocon.ru` | **Оставить** (пойдёт за новым A) |
| `hoocon.ru` | MX | `10 mx.yandex.net` | **Оставить** |
| `hoocon.ru` | TXT | `v=spf1 redirect=_spf.yandex.net` | **Оставить** |
| `mail._domainkey.hoocon.ru` | TXT | `v=DKIM1; k=rsa; t=s; p=MIGf…` (полный ключ в панели) | **Оставить** |
| `hoocon.ru` | TXT | `yandex-verification: bb738f87fa6f7bfa` | **Оставить** (Вебмастер) |
| `hoocon.ru` | TXT | `google-site-verification=lfzbxPcfbap_s_bhWCOZ6zTP3UZvEnZm_lQA4ASrYlo` | **Оставить** (GSC) |
| `hoocon.ru` | TXT | `globalsign-domain-verification=nU52DBYgUfXw71Imrf9q6i2KqNgwiFvXYMeZL3F0yr` | **Оставить**, пока нужен TLS/каб. GlobalSign |

**Нет в снимке:** `_dmarc` — добавить по желанию после cutover
(`v=DMARC1; p=none; rua=mailto:dmarc@hoocon.ru`).

### 4.1 Где править зону (важно)

Пока NS указывают на Tilda (`ns*.tildadns.com` или аналог) — правки
только в DNS Tilda. После ухода с Tilda **нельзя** оставить зону там:

1. **До или в день cutover:** перенести управление DNS на **reg.ru**
   (NS регистратора) и **пересоздать все строки** из таблицы выше
   (почта + verification + `www` CNAME) + новый A на VPS.
2. Либо временно сменить только A в Tilda на IP VPS (сайт поедет на
   CMS, почта жива), но затем всё равно увести NS с Tilda — иначе
   зависимость от чужой панели после отключения сайта.

Проверка NS: `dig NS hoocon.ru +short`.

---

## 5. Подключение домена к сайту (A → VPS)

Цель: `hoocon.ru` / `www.hoocon.ru` открывают CMS на VPS, а не Tilda.
Почту при этом **не трогаем** (MX/SPF/DKIM уже рабочие).

### 5.1 Подготовка

1. Зафиксировать **публичный IPv4** (и при наличии IPv6) VPS.
2. **За 24–48 ч до cutover** снизить TTL у A / CNAME сайта
   (например до 300 с).
3. Параллельный прогон: сайт по IP (`Host: hoocon.ru`), полный
   URL-inventory — потом смена A.
4. Перенести зону на reg.ru (§4.1) **или** сменить A в Tilda, если
   cutover в два шага.

### 5.2 Записи сайта после cutover

| Тип | Хост | Значение | Примечание |
|-----|------|----------|------------|
| A | `@` / `hoocon.ru` | `<IPv4 VPS>` | вместо `176.57.64.46` |
| CNAME | `www` | `hoocon.ru` | как сейчас |
| AAAA | `@` / `www` | `<IPv6 VPS>` | только если nginx слушает IPv6 |

### 5.3 TLS и nginx

1. После смены A: Let's Encrypt для `hoocon.ru` + `www`.
2. HTTP→HTTPS; HSTS — **после** стабилизации.
3. В `.env` на VPS: `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` с
   `https://hoocon.ru` и `https://www.hoocon.ru`.
4. Smoke: `/`, `/catalog`, SKU, RFQ, `/api/health/` по HTTPS.

Подробнее редиректы SEO: [seo-url-migration.md](seo-url-migration.md).

---

## 6. Почта (Яндекс 360) — уже в DNS; SMTP в приложение

Цель: оставить ящики `*@hoocon.ru` на Яндекс 360; Django шлёт через
SMTP 360. **DNS почты с Tilda уже совпадает с каноном Яндекса** —
пересоздать в reg.ru 1:1 при переносе зоны, не выдумывать заново.

### 6.1 Организация 360

1. Убедиться, что `hoocon.ru` в
   [Яндекс 360](https://360.yandex.ru/business/) в статусе подтверждён
   (TXT `yandex-verification: …` уже есть).
2. **Не** делегировать NS на Яндекс — зона на reg.ru после ухода с Tilda.
3. В кабинете 360 проверить, что MX/SPF/DKIM «зелёные» после переноса
   записей на reg.ru (`dig MX` / `dig TXT`).

### 6.2 Эталон почтовых записей (из текущего снимка)

| Тип | Хост | Значение |
|-----|------|----------|
| MX | `@` | `mx.yandex.net.` приоритет **10** |
| TXT | `@` | `v=spf1 redirect=_spf.yandex.net` |
| TXT | `mail._domainkey` | тот же DKIM `p=…`, что в панели Tilda / 360 |

Опционально: `_dmarc` (см. §4). Одна SPF на `@` — уже так; не добавлять
вторую SPF от reg.ru.

Если кабинет 360 покажет **новый** DKIM-ключ — брать ключ из 360, не
из старого снимка.

### 6.3 Ящики

| Ящик | Тип в 360 | Назначение |
|------|-----------|------------|
| `sales@hoocon.ru` | **общий** ящик отдела | Inbox заявок / менеджеры (`LEAD_NOTIFY_EMAIL`) |
| `noreply@hoocon.ru` | **обычный** (сервисный) | SMTP Django/Celery; `From` системных писем |
| `info@` / др. | по необходимости | сайт, партнёры |
| `dmarc@hoocon.ru` | опц. | отчёты DMARC |

**Почему не SMTP с `sales@`:** у общего ящика отдела нет своего Яндекс ID →
пароль приложения не создать. Алиас `noreply`→`sales` тоже не даёт SMTP.
Нужен отдельный обычный ящик `noreply@` (или `cms@` / `bot@`).

Завести в 360: сотрудник/ящик `noreply` → включить IMAP + пароли
приложений → пароль приложения «Почта». Входящие на `noreply@` можно
фильтром складывать / игнорировать (ответы клиентам — с `sales@` вручную).

### 6.4 SMTP для Django (пароль приложения `noreply@`)

1. Войти в веб-почту **`noreply@hoocon.ru`**: **Настройки → Почтовые
   программы** — IMAP; **пароли приложений и OAuth-токены**.
2. В [Яндекс ID → пароли приложений](https://id.yandex.ru/security/app-passwords)
   (аккаунт `noreply`) создать пароль для «Почта».
3. На VPS в `.env` (не коммитить):

```bash
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_USE_TLS=False
EMAIL_HOST_USER=noreply@hoocon.ru
EMAIL_HOST_PASSWORD=<пароль_приложения_noreply>
DEFAULT_FROM_EMAIL=noreply@hoocon.ru
LEAD_NOTIFY_EMAIL=sales@hoocon.ru
```

4. Перезапустить `web` + `celery_worker`. Тест Lead → Inbox `sales@`
   (From = `noreply@`).
5. Логин SMTP — полный `noreply@hoocon.ru`.

CRM «Написать письмо» клиенту в v1 тоже уйдёт с `noreply@` (тот же
`DEFAULT_FROM_EMAIL`). Ответы клиентов на такое письмо попадут в
`noreply@` — смотреть Inbox сервиса или позже настроить «Отправить как
sales@» (не блокер cutover).

Альтернатива: порт 587 + STARTTLS, если 465 закрыт с VPS.

### 6.5 Клиенты сотрудников (Thunderbird / Outlook)

| | Входящая | Исходящая |
|--|----------|-----------|
| Сервер | `imap.yandex.ru` | `smtp.yandex.ru` |
| Порт / SSL | 993 / SSL | 465 / SSL |
| Логин | полный `user@hoocon.ru` | то же |
| Пароль | пароль приложения | то же |

---

## 7. Чеклист cutover (когда MVP готов)

- [ ] Снимок DNS сохранён (§4); NS решение: reg.ru vs временно Tilda
- [ ] TTL A снижен заранее
- [ ] Зона на reg.ru с **полным** набором записей §4 **или** A сменён в Tilda
- [ ] A `hoocon.ru` → IPv4 VPS (не `176.57.64.46`); `www` CNAME жив
- [ ] MX / SPF / DKIM **без изменений** и зелёные в кабинете 360
- [ ] Verification TXT (Yandex / Google / GlobalSign) перенесены
- [ ] TLS валиден; HSTS — после стабилизации
- [ ] Ящик `noreply@` (обычный) + пароль приложения в `.env`; тест Lead → `sales@`
- [x] **SEO:** инвентарь URL 200/301 **по IP**
      ([seo-url-migration.md](seo-url-migration.md) §5;
      `scripts/check-url-inventory.sh`) — полный после DNS
- [ ] Метрика / Вебмастер на новом origin
- [ ] Smoke: `/`, `/catalog`, SKU, форма RFQ, `/api/health/`
- [x] Бэкап скрипт + cron на VPS (`scripts/backup-vps.sh`)
- [ ] После отключения Tilda: NS **не** на `tildadns` (§4.1)

Rollback web: A снова на `176.57.64.46`. Почту при cutover не откатываем,
если MX не трогали.

---

## 8. Риски

| Риск | Митигация |
|------|-----------|
| Малый VPS / OOM | лимиты workers, swap осторожно, мониторинг |
| Доставляемость почты | SPF/DKIM уже есть; SMTP только через 360 |
| Потеря MX/TXT при переносе зоны | копировать §4 1:1; не чистить «лишние» TXT |
| Зона осталась на Tilda после ухода | увести NS на reg.ru до отключения сайта |
| Downtime cutover | параллельный прогон, низкий TTL, rollback A |
| Смена почты через ~год | DNS + `.env` SMTP; ящики мигрировать заранее |
| DDoS-Guard у Tilda сейчас | fail2ban / лимиты nginx; защита reg.ru по нужде |

---

## 9. Бэкапы (Postgres + media)

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

## 10. Мониторинг (минимум до Sentry)

Скрипт: [`scripts/monitor-health.sh`](../scripts/monitor-health.sh) —
`curl` `/api/health/` + порог заполнения диска (`DISK_WARN_PCT=85`).

```cron
*/5 * * * * HEALTH_URL=http://127.0.0.1:8000/api/health/ \
  /opt/hoocon/scripts/monitor-health.sh
```

Лог: `/var/log/hoocon-monitor.log`. Ненулевой exit → mail от cron (если
настроен). Sentry — после стабилизации (Iter 6).

---

## 11. Отложено до cutover сайта / SMTP в приложение

DNS-почта Яндекс уже в бою (§4). Пока **сайт** на Tilda и Django не
шлёт через `smtp.yandex.ru`, в коде/проде CMS **не** делать:

- TLS Let’s Encrypt «в бою» на VPS, HSTS, HTTP→HTTPS redirect
- SMTP smoke Lead/CRM с VPS (пароль приложения в `.env`)
- Client auth / ЛК / чат поддержки
- **AnalogMap / `/analog-belimo`** — только после валидированной карты
  ([data-quality-etl.md](data-quality-etl.md)); сейчас лишь
  `SKU.analog_belimo_code` + ETL heuristics

Связано: [market-analysis.md](market-analysis.md), план проекта (scope / infra).
