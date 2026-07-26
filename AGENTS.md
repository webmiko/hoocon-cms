# AGENTS.md

> В этом проекте используется автономная база знаний (стиль кода по PEP 8 + Zen of
> Python, типизация PEP 585/604, безопасность, масштабируемость, процесс разработки
> и примеры кода).
>
> **Начни отсюда (канон БЗ):** [_Универсальная-база-знаний/AGENTS.md][kb-agents]
>
> Там — золотые правила (§0), маршрутизация (§1), иерархия документов (§2),
> каркас модуля (§3), **чеклист коммита/деплоя (§4)**, пополнение БЗ (§5–6).
> Этот файл — тонкая обёртка репозитория; **не дублирует** канон.

## Правила для ИИ

1. При любой задаче по коду **сначала** прочитай [канон AGENTS.md][kb-agents] и
   следуй золотым правилам (§0) и маршрутизации (§1).
2. База знаний имеет **высший приоритет** над привычками: стиль, типизация,
   безопасность и масштабируемость берём из неё.
3. Пути внутри базы знаний указаны **относительно папки**
   `_Универсальная-база-знаний/`.
4. Не меняй одобренный код без явного запроса; не делай `git add` автоматически;
   даты — текущий год системы пользователя (`ГГГГ-ММ-ДД`).
5. По завершении задачи переносимые решения добавляй в базу по
   [инструкции обновления БЗ][kb-update].
6. Перед **каждым** `git commit` / `git push` / деплоем:
   - пройди канон [AGENTS.md §4][kb-agents];
   - запусти `./scripts/pre-commit-checkup.sh` (правило
     `.cursor/rules/pre-commit-checkup.mdc`), включая ревью diff
     (баги / стандарты БЗ / security через `scripts/diff-quality-review.py`);
   - при **новой фиче** подними релиз по [docs/releases.md](docs/releases.md)
     (сейчас `v0.0.x beta`);
   - учитывай проектный [docs/security-baseline.md][sec-baseline].
   Красный checkup, красное ревью или критичный пункт §4 — **не коммить**.

## Проект Hoocon CMS

B2B-сайт и CMS для HVAC (электроприводы ОВК): каталог, фильтры, поиск,
контент, заявки RFQ. **Без онлайн-корзины и оплаты в v1.**

| Документ | Назначение |
|----------|------------|
| [ПЛАН-ПРОЕКТА.md](ПЛАН-ПРОЕКТА.md) | Scope, итерации, решения |
| [docs/](docs/) | Рынок, стек, SEO URL, ETL, UX, security, infra reg.ru, audit |
| [docs/releases.md](docs/releases.md) | Версии Admin/фронт (`v0.0.x beta` → `1.0.0`) |
| [docs/audit-2026-07-20.md](docs/audit-2026-07-20.md) | Аудит баги/БЗ/security + статус фиксов A–E |
| [docs/security-baseline.md][sec-baseline] | OWASP 2025 → Hoocon |
| [docs/seo-url-migration.md](docs/seo-url-migration.md) | Сохранение URL и 301 |
| [docs/seo-meta-yandex-google.md](docs/seo-meta-yandex-google.md) | Title/description для Яндекс и Google |
| [docs/tech-copy-belimo-ru.md](docs/tech-copy-belimo-ru.md) | Канон терминологии ТТХ / инструкций (Belimo RU) |
| [docs/series-card-templates.md](docs/series-card-templates.md) | Шаблоны карточек DA / SA / 8100 / H81 / H8205 |
| `../hoocon/` | Tilda-контент и данные каталога (соседний репо) |

Стек: Django + DRF + Postgres + Celery/Redis; React + Vite; prod — VPS/DNS/mail
**reg.ru**. Python 3.12–3.13 → инструкция БЗ **v2.0**.

### Маршрутизация по задаче (дополнение к БЗ §1)

| Задача | Куда |
|--------|------|
| Коммит / push | `./scripts/pre-commit-checkup.sh` + канон §4 |
| Релиз / версия | [docs/releases.md](docs/releases.md); `config/release.py` |
| Admin / Unfold / CMS-панель | БЗ [ОПЫТ-UNFOLD-ADMIN-HOOCON][kb-unfold]; рецепты [ПАТТЕРНЫ][kb-unfold-patterns] |
| Аудит / hardening backlog | [docs/audit-2026-07-20.md](docs/audit-2026-07-20.md); план Iter 4.5–5 |
| Новый код / модуль | БЗ ПРОМПТ + TDD; apps в `backend/` |
| Каталог / SKU / фильтры | План итерация 1; [plan-detail-mvp.md](docs/plan-detail-mvp.md) |
| Карточка серии (DA/SA/8100/H81/H8205) | [series-card-templates.md](docs/series-card-templates.md) |
| Чат поддержки (TG/VK/MAX) | [plan-support-chat-social.md](docs/plan-support-chat-social.md) |
| Регистрация клиентов (пароль / OTP / Яндекс ID) | [plan-client-auth.md](docs/plan-client-auth.md) |
| Личный кабинет (КП / обращения / статусы) | [plan-client-cabinet.md](docs/plan-client-cabinet.md) |
| SEO / редиректы | [seo-url-migration.md](docs/seo-url-migration.md) |
| Title / description (Яндекс, Google) | [seo-meta-yandex-google.md](docs/seo-meta-yandex-google.md) |
| ТТХ / инструкции / перевод | [tech-copy-belimo-ru.md](docs/tech-copy-belimo-ru.md) |
| ETL / качество данных | [data-quality-etl.md](docs/data-quality-etl.md) |
| UX / дизайн B2B | [readiness-backend-ux.md](docs/readiness-backend-ux.md); прототипы `../hoocon/docs/прототипы/` |
| Статьи / лендинги (графики) | `.cursor/rules/cms-content-dashboards.mdc`; стили `frontend/src/styles/cms-body-charts.css`; референс `/zavod` |
| Веб / SEO SPA | БЗ `ВЕБ-РАЗРАБОТКА-Кастомный-стек/` |
| Безопасность | БЗ `безопасность/` + [security-baseline.md][sec-baseline] |
| Деплой / VPS | [infra-reg-ru.md](docs/infra-reg-ru.md); LMS-референс в БЗ |
| Paywall / Stripe | **Не в scope v1.** Модуль БЗ — только если явно попросят позже |

## Иерархия при конфликте

1. Золотые правила канона БЗ (§0).
2. Методики и примеры БЗ (§2 канона).
3. Стандарты БЗ (ПРОМПТ, безопасность).
4. Договорённости этого репо (`ПЛАН-ПРОЕКТА.md`, `docs/`, Cursor rules) —
   если не противоречат п. 1–3.

[kb-agents]: _Универсальная-база-знаний/AGENTS.md
[kb-update]: _Универсальная-база-знаний/ИНСТРУКЦИЯ-ПО-ОБНОВЛЕНИЮ-БАЗЫ-ЗНАНИЙ.md
[kb-unfold]: _Универсальная-база-знаний/02-Примеры-кода/hoocon-cms/ОПЫТ-UNFOLD-ADMIN-HOOCON.md
[kb-unfold-patterns]: _Универсальная-база-знаний/02-Примеры-кода/hoocon-cms/ПАТТЕРНЫ-UNFOLD-ADMIN.md
[sec-baseline]: docs/security-baseline.md
