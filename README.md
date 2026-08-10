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

## Репозиторий

```text
backend/     Django apps (catalog, leads, search, …), API, ETL
frontend/    Публичный SPA
docs/        Проектная документация (wiki-индекс: docs/README.md)
scripts/     Checkup, деплой-хелперы
```

## Документация

Полный индекс (wiki в репозитории): [`docs/README.md`](docs/README.md).

Ключевые темы:

| Тема | Файл |
|------|------|
| Версии релизов | [docs/releases.md](docs/releases.md) |
| Безопасность | [docs/security-baseline.md](docs/security-baseline.md) |
| SEO / URL | [docs/seo-url-migration.md](docs/seo-url-migration.md) |
| Инфраструктура | [docs/infra-reg-ru.md](docs/infra-reg-ru.md) |
| ETL / качество данных | [docs/data-quality-etl.md](docs/data-quality-etl.md) |
| Карточки серий | [docs/series-card-templates.md](docs/series-card-templates.md) |

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
на ветке `develop`. Версия продукта — см. [docs/releases.md](docs/releases.md).
