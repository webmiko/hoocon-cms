# Чеклист безопасности прода (hoocon.ru)

Раз в релиз и при смене `.env` на VPS. Код-защита уже в репо —
этот файл про то, что включается **только конфигом/операциями**,
иначе защита молча выключена.

## 1. Админка: OTP / passkey (CFG-1)

В `/opt/hoocon/.env` на VPS должно быть включено хотя бы одно:

```bash
ADMIN_EMAIL_OTP_ENABLED=True     # одноразовый код на почту
ADMIN_PASSKEY_ENABLED=True       # WebAuthn-ключ
```

- [ ] Проверить `grep -E 'ADMIN_(EMAIL_OTP|PASSKEY)_ENABLED' .env` — не `False`
- [ ] Вход в `/admin/` реально требует второй фактор (smoke под своим пользователем)
- [ ] `AXES_FAILURE_LIMIT=5` активен — смотреть `django-axes` блокировки в логах
      (`docker compose logs web | grep -i axes`), ложные блокировки снимать из админки

## 2. Staff API (мобильное CRM) (CFG-2)

```bash
STAFF_API_ENABLED=False   # включать ТОЛЬКО если мобильное приложение в работе
```

При `STAFF_API_ENABLED=False` эндпоинты отдают 404 — это норма, не поломка.

- [ ] `STAFF_API_ENABLED` выключен, если мобильный клиент не используется
- [ ] Если включён: `STAFF_API_TOKEN_TTL_DAYS` ≤ 90, токены — hashed (уже в коде)
- [ ] Ротация: раз в квартал перевыпустить токены сотрудникам
      (старый отзывается автоматически), при увольнении — отозвать немедленно
- [ ] Утечка токена = полный доступ к мобильной CRM → инцидент-процедура:
      удалить `StaffAuthToken` сотрудника в админке

## 3. Бэкапы вне VPS (CFG-3)

`scripts/backup-vps.sh` кладёт dump+media+private_media в
`${DEPLOY_PATH}/backups/` **на том же хосте** — при потере VPS теряется всё.

- [ ] Nightly `backup-vps.sh` по cron (03:00 UTC, `deploy/cron/hoocon-vps.cron`)
- [ ] Синк наружу: раз в день `rsync`/`rclone` каталога `backups/` на
      внешнее хранилище (второй хост / S3-совместимое / офисный NAS)
      — отдельно от VPS, с другими креденшелами
- [ ] `private_media.tar.gz` — PII и документы: шифрованное хранилище,
      доступ только у владельца (chmod 600 уже в скрипте)
- [ ] Restore drill раз в квартал по `deploy/ops/backups-restore.md`

## 4. Ограничения и лимиты (зафиксировано в коде)

Сверить, что в `.env` не переопределено на слабые значения:

- [ ] `SUPPORT_ATTACHMENT_MAX_FILES` не выкручен выше default 20
      (env-настройка, `int` в settings.py); per-IP scope `support_attachment`
      — 20/day в `DEFAULT_THROTTLE_RATES`
- [ ] Throttle-рейты в `settings.DEFAULT_THROTTLE_RATES` не ослаблены в `.env`
- [ ] `DEBUG=False`, `SECRET_KEY` — не дефолт/не из репо

## 5. Входящая почта CRM (M1-остаток, осознанно принят)

`crm/imap_fetch.py` пишет EMAIL-активность на карточку по `From:` — заголовок
подделывается без аутентификации на приёме. Код-гейт намеренно не ставится:
это фидельная запись реально полученного письма, блокировка = отключение
логирования почты в CRM.

- [ ] На почтовом ящике CRM-ящика включён reject по SPF/DKIM/DMARC
      (не «mark as spam»), в идеале DMARC p=reject на hoocon.ru
- [ ] Менеджеры знают: текст EMAIL-активности — untrusted, как и любое письмо

## 6. После выката security-фиксов

- [ ] `post-deploy-checklist.md` пройден
- [ ] Лог-аномалии за сутки: всплески 429 на `/api/leads/`, `/api/support/`
      (абьюз продолжался?). 404 на `GET /api/quotes/reply/` — ожидаемо для
      запросов без заголовка; старые письма работают, т.к. SPA переносит
      `?t=`/`#t=` из URL в `X-Quote-Token` на клиенте.
