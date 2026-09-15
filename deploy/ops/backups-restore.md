# Бэкапы и восстановление (VPS)

Канон для nightly-бэкапов: `scripts/backup-vps.sh`, cron в
`deploy/cron/hoocon-vps.cron` (03:00 UTC).

## Что бэкапится

- Postgres dump (`hoocon.dump`, custom format)
- `media/` как `media.tar.gz` (если путь существует на хосте)

Хранение по умолчанию: 7 дней в `${DEPLOY_PATH}/backups/`.

## Ручной бэкап

```bash
ssh hoocon-prod '/opt/hoocon/scripts/backup-vps.sh'
```

## Восстановление БД (drill на staging / аварийно)

1. Остановить web/celery (чтобы не писали в БД).
2. Выбрать каталог бэкапа: `/opt/hoocon/backups/YYYYMMDDTHHMMSSZ/`.
3. Восстановить dump в Postgres (через `docker compose exec db` на VPS).
4. Поднять web/celery, проверить `/api/health/` и выборочно SKU в Admin.

Перед `sync-db-to-vps.sh` на прод всегда выполняется `backup-vps.sh` на VPS.

## Проверка раз в квартал

- [ ] Ручной бэкап завершился (`COMPLETED` в каталоге)
- [ ] Restore drill на копии/staging (не на live prod без окна)
- [ ] Retention удаляет каталоги старше 7 дней
