# Hoocon CMS

B2B-сайт и CMS для HVAC (электроприводы ОВК): каталог с фильтрами, поиск,
контент, заявки RFQ. Замена Tilda-сайта [hoocon.ru](https://hoocon.ru).

**Без онлайн-корзины и оплаты в v1** — заявки RFQ вместо checkout.

## Стек

| Слой | Выбор |
|------|--------|
| Backend | Django + DRF, PostgreSQL, Celery / Redis |
| Admin | Django Admin (Unfold) |
| Frontend | React + TypeScript + Vite |
| Prod | VPS / DNS **reg.ru** + почта **Яндекс 360**, Docker Compose, GitHub Actions |

Python 3.12–3.13.

**Лицензия:** проприетарная, все права защищены — [LICENSE](LICENSE).  
**Безопасность:** [SECURITY.md](SECURITY.md) · локально `_docs/security-baseline.md`.

## Репозиторий

```text
backend/     Django apps (catalog, leads, search, …), API, ETL
frontend/    Публичный SPA
_docs/       Проектная документация (локально, не в git; индекс: _docs/README.md)
scripts/     Checkup, деплой-хелперы
```

## Документация

Полный индекс (локально): `_docs/README.md` (каталог `_docs/` в git не
попадает — см. `.gitignore`).

Ключевые темы:

| Тема | Файл (локально) |
|------|-----------------|
| Версии релизов | `_docs/releases.md` |
| Безопасность | `_docs/security-baseline.md` · [SECURITY.md](SECURITY.md) |
| Лицензия | [LICENSE](LICENSE) (проприетарная) |
| SEO / URL | `_docs/seo-url-migration.md` |
| Инфраструктура | `_docs/infra-reg-ru.md` |
| ETL / качество данных | `_docs/data-quality-etl.md` |
| Карточки серий | `_docs/series-card-templates.md` |

## Локальный запуск (кратко)

```bash
# Backend
cp .env.example .env   # заполнить секреты локально, не коммитить
cd backend && poetry install
poetry run python manage.py migrate
poetry run python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev
```

Docker: `docker-compose.yml` (dev) / `docker-compose.prod.yml` (prod).

Перед коммитом: `./scripts/pre-commit-checkup.sh`.

## Статус

Публичный каталог, поиск, RFQ, Admin/ETL и деплой на reg.ru в работе
на ветке `develop`. Версия продукта — см. `_docs/releases.md` (локально).
