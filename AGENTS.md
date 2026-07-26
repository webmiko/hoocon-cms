# AGENTS.md

> Канон стиля/безопасности: [_Универсальная-база-знаний/AGENTS.md][kb-agents]
> (симлинк). Этот файл — **тонкая обёртка** репозитория; не дублирует канон.

## Как грузить контекст (не тяни лишнее)

| Задача | Что читать |
|--------|------------|
| Любой код | Этот файл + строка маршрутизации ниже |
| Python / Django / ETL / API | Канон БЗ **§0** (золотые правила); §4 — только перед commit |
| Публичный UI / CSS / SPA-страницы | + правило `frontend-public-ui.mdc`; БЗ правило **12** (Lighthouse) |
| Новый модуль / TDD | БЗ ПРОМПТ + Pytest |
| Коммит / push / **`чкд`** | `./scripts/pre-commit-checkup.sh` (скрипт сам гоняет FE lint **только** при diff в `frontend/`) |
| Карточки серий DA/SA/8100/H81/H8205 | [series-card-templates.md](docs/series-card-templates.md) |
| Релиз | [docs/releases.md](docs/releases.md) |

**Не** открывай веб-промпты / Lighthouse / CWV на чисто бэкенд-задачах
(ETL, Admin, API без HTML/CSS).

Минимальный diff; YAGNI; багфикс — через callers (правило `bugfix-dependencies.mdc`).

## Правила для ИИ

1. База знаний важнее привычек модели (стиль PEP 585/604, security).
2. Пути в БЗ — относительно `_Универсальная-база-знаний/`.
3. Не меняй одобренный код без запроса; не `git add` сам; даты —
   текущий год (`ГГГГ-ММ-ДД`).
4. Переносимые паттерны — в канон по [инструкции][kb-update].
5. Перед **каждым** commit / push: зелёный
   `./scripts/pre-commit-checkup.sh`; рукописное ревью — **только по
   поверхности diff** (бэкенд ≠ UI/Lighthouse). Красный checkup — не коммить.
6. Новая фича → релиз по [docs/releases.md](docs/releases.md).
7. **Без корзины/оплаты в v1** — RFQ вместо checkout.

## Проект

B2B HVAC CMS: каталог, фильтры, поиск, контент, RFQ.
Стек: Django + DRF + Postgres + Celery/Redis; React + Vite; prod — reg.ru.

| Документ | Назначение |
|----------|------------|
| [ПЛАН-ПРОЕКТА.md](ПЛАН-ПРОЕКТА.md) | Scope, итерации |
| [docs/](docs/) | SEO, ETL, UX, security, infra, audit |
| [docs/releases.md](docs/releases.md) | Версии (beta → `vMAJOR.MINOR`) |
| [docs/security-baseline.md][sec-baseline] | OWASP → Hoocon |
| `../hoocon/` | Tilda-данные (соседний репо) |

### Маршрутизация

| Задача | Куда |
|--------|------|
| Коммит / **`чкд`** | `pre-commit-checkup.sh` + `chkd-checkup-commit-deploy.mdc` |
| Релиз | `docs/releases.md`; `config/release.py` |
| Admin / Unfold | БЗ [ОПЫТ-UNFOLD][kb-unfold]; [ПАТТЕРНЫ][kb-unfold-patterns] |
| Каталог / серии | `docs/series-card-templates.md` |
| SEO / meta | `docs/seo-url-migration.md`, `docs/seo-meta-yandex-google.md` |
| ТТХ / ё | `docs/tech-copy-belimo-ru.md`; `russian-yo.mdc` |
| ETL | `docs/data-quality-etl.md` |
| Безопасность | БЗ `безопасность/` + [security-baseline.md][sec-baseline] |
| Деплой | `docs/infra-reg-ru.md` |
| Paywall | **Не в v1** |

## Иерархия при конфликте

1. Золотые правила БЗ (§0).
2. Методики / стандарты БЗ.
3. Этот репо (`ПЛАН`, `docs/`, `.cursor/rules`) — если не противоречат п. 1–2.

[kb-agents]: _Универсальная-база-знаний/AGENTS.md
[kb-update]: _Универсальная-база-знаний/ИНСТРУКЦИЯ-ПО-ОБНОВЛЕНИЮ-БАЗЫ-ЗНАНИЙ.md
[kb-unfold]: _Универсальная-база-знаний/02-Примеры-кода/hoocon-cms/ОПЫТ-UNFOLD-ADMIN-HOOCON.md
[kb-unfold-patterns]: _Универсальная-база-знаний/02-Примеры-кода/hoocon-cms/ПАТТЕРНЫ-UNFOLD-ADMIN.md
[sec-baseline]: docs/security-baseline.md
