# Детализация плана MVP: боль → фича → тест

Дата: 2026-07-19  
Базовый план: план проекта (scope / MVP-критерии).  
Контекст: [market-analysis.md](market-analysis.md),
[seo-url-migration.md](seo-url-migration.md),
[infra-reg-ru.md](infra-reg-ru.md).  
Метод БЗ: декомпозиция + TDD (red → green → refactor).

---

## §2 Scope — каждый пункт MVP

| # | Пункт scope | Боль клиента / бизнеса | Фича / артефакт | Тест / приёмка |
|---|-------------|------------------------|-----------------|----------------|
| S1 | Каталог Category/Product/SKU/атрибуты/PDF | B2/B3: не найти модель и документ | Django models + Admin + ProductFile | pytest модели; Admin smoke |
| S2 | Фильтры + URL state | B2: момент / 24\|230 / пружина | DRF filterset; query на `/catalog` | API-тесты фильтров; e2e URL |
| S3 | Postgres FTS | Навигация по артикулам/статьям | SearchVector на SKU+Article | pytest: SKU и статья находятся |
| S4 | Page / News / Article | Контент без деплоя; E-E-A-T | apps `content`; Admin | staff правит → 200 на slug |
| S5 | Формы RFQ / консультация / замена | B4: заявка вместо корзины | `leads.Lead` + Celery email | POST → Lead; mock SMTP |
| S6 | React + SEO гибрид | B6: Tilda JS / индексация | SPA + `spa_index_view` head | title в HTML без JS; Lighthouse |
| S7 | ETL из `../hoocon/data/` | Перенос **всей** номенклатуры **без** ошибок Tilda | scripts/etl + validate/quarantine | count = total; гейты data-quality |
| S8 | Docker local + CI | Качество | compose db/redis; GHA | ruff/mypy/pytest green |
| S9 | Цены в БД, скрыты + флаг | Дилеры открывают цены; мы — по политике | `SiteSettings.show_prices` | API без цены по умолчанию |
| S10 | Git private; prod после MVP | Контроль релиза | remote private | — |
| S11 | VPS/DNS/mail reg.ru | Одна платформа | compose+nginx+SMTP | письмо Lead на sales@ |
| S12 | **SEO URL / 301** | Не потерять позиции | slug 1:1 + Redirect + nginx | инвентарь 200/301 |

Вне v1 без изменений: корзина, ЛК дилера, BIM, EN, Meilisearch, Wagtail.

---

## §3 Критерии готовности MVP (расширение)

| # | Критерий | Доказательство |
|---|----------|----------------|
| M1 | Каталог = **вся** номенклатура ETL (не сэмпл) | UI + pytest; count ≥ store total |
| M2 | Карточка: ТТХ, ≥1 PDF, Lead | E2E форма |
| M3 | Статья и «О компании» из Admin | slug `/statyi/…`, `/company` |
| M4 | CWV/smoke + уникальные title | Lighthouse; head в HTML |
| M5 | pytest catalog+leads; ruff/mypy CI | GHA green |
| M6 | **Все path из seo-url §2.1 → 200** | curl/pytest redirects |
| M7 | **Все `/tproduct/…` из карты → 301** | pytest Redirect |
| M8 | SMTP Lead через ящик reg.ru (staging/prod) | лог Celery + входящее |

**N = вся продукция каталога.** Снимок 2026-07-19: `total=39` в
`../hoocon/data/hoocon_catalog_api.json` (25 ЧПУ `/privod-*` + 14
`/tproduct/…`, в т.ч. BV* → `/sharovoy-kran-bv…`). При ETL — полный
импорт; при росте ассортимента на Tilda до cutover — переснять API/
sitemap и догрузить.

Шаблон ЧПУ кранов (**утверждено**): `/sharovoy-kran-{артикул}` —
карта 301: [redirects-tproduct-seed.csv](redirects-tproduct-seed.csv).

---

## §4 Стек — следствия

| Слой | Выбор | Следствие для SEO/infra |
|------|-------|-------------------------|
| Backend | Django+DRF | `slug`, Redirect, spa head, FTS |
| DB | Postgres | FTS; один инстанс на VPS |
| Queue | Celery+Redis | email через SMTP reg.ru |
| Front | React+Vite | маршруты = старые path |
| Edge | nginx на VPS | 301 map, TLS, CSP, static |
| Search v1 | Postgres FTS | без Meilisearch на маленьком VPS |

---

## §5 Структура репо — дополнения под SEO/ETL

```
hoocon-cms/
├── backend/           # Django; apps: catalog, content, leads, search
├── frontend/          # маршруты под /catalog, /privod-*, /statyi, …
├── docs/              # план, рынок, seo-url-migration, infra
├── scripts/
│   ├── etl_hoocon_data.py
│   └── export_tilda_redirects.py   # sitemap-store → CSV
└── deploy/nginx/      # redirects.map, spa.conf (как LMS)
```

---

## §6 Итерации — задачи с тестами

### Итерация 0 (каркас) — почти закрыта

Добить: `.env.example` SMTP-поля; заготовка `deploy/nginx/` (можно stub).

### Итерация 1 — каталог (+ SEO slug)

| Задача | Боль | Тест |
|--------|------|------|
| Модели + `slug` unique | B2 | factory + constraints |
| Admin каталога | менеджер | smoke |
| API list/detail + filters | B2 | pytest filter matrix |
| ETL: SKU со **старыми slug** + validate | SEO + качество | assert slug; quarantine bad rows |
| Модель `Redirect` + import CSV | tproduct | pytest 301 logic |

### Итерация 2 — поиск и медиа

| Задача | Боль | Тест |
|--------|------|------|
| FTS SKU+Article | поиск | query → hit |
| ProductFile PDF/cert | B3 | download 200; auth public read |
| sitemap.xml generator | SEO | только canonical paths |

### Итерация 3 — контент и лиды

| Задача | Боль | Тест |
|--------|------|------|
| Page/Article/News со slug | контент/SEO | `/company`, `/statyi` |
| Lead + Celery email | B4 | on_commit + mailoutbox |
| honeypot + throttle | спам | 429 / silent drop |

### Итерация 4 — публичный фронт

| Задача | Боль | Тест |
|--------|------|------|
| Маршруты = старые path | SEO | router ↔ slug |
| Фильтры ↔ query | B2 | shareable URL |
| Формы RFQ | B4 | success UX + Lead |
| spa_index_view + JSON-LD Product | SEO БЗ | HTML содержит title/jsonld |
| Без Cart/Wishlist иконок | B7 | UI review |

### Итерация 5 — prod reg.ru + редиректы

| Задача | Боль | Тест |
|--------|------|------|
| nginx TLS CSP | infra | curl https |
| redirects.map из Redirect | SEO | полный инвентарь |
| SMTP reg.ru | лиды | реальное письмо |
| CI + deploy SSH | качество | pipeline |
| Cutover чеклист | риск | [seo-url §5](seo-url-migration.md) |

### Итерация 6+

Сравнение; подбор/замена; `/analog-belimo`; Meilisearch; EN —
не ломая каноны v1.

---

## Риски SEO (дополнение к плану §7)

| Риск | Митигация |
|------|-----------|
| Сменили slug «для красоты» | Запрет без Redirect; code review |
| Забыли `/tproduct/` | ETL скрипт + CI тест на CSV |
| Query-фильтры в индексе | canonical на `/catalog` |
| Параллельный Tilda+новый | один canonical host после DNS |

---

## Статус детализации

- [x] §2 scope → боль → фича → тест
- [x] §3 критерии + SEO M6–M8
- [x] §4–§5 следствия
- [x] §6 итерации с SEO/редиректами
- [x] Документ URL/301: [seo-url-migration.md](seo-url-migration.md)
- [x] ЧПУ BV*: `/sharovoy-kran-bv215` + seed CSV
- [x] N = вся продукция каталога (~39 SKU)

Следующий шаг: старт **итерации 1** (модели + slug + Redirect + ETL).
