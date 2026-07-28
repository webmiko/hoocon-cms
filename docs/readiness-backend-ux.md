# Готовность, бэкенд и UX/дизайн B2B (перед итерацией 1)

Дата: 2026-07-19  
Цель: понять, **всё ли есть** для старта кода; как строим backend;
какой UX/дизайн берём с учётом успеха и болей HVAC.

Связано: [market-analysis.md](market-analysis.md),
[plan-detail-mvp.md](plan-detail-mvp.md),
[stack-decision.md](stack-decision.md),
[seo-url-migration.md](seo-url-migration.md),
[infra-reg-ru.md](infra-reg-ru.md).  
Прототипы UX: `../hoocon/docs/прототипы/`
(главная, каталог, товар, `prototip-hoocon-shared.css`).

---

## 1. Всё ли у нас есть? (чеклист)

### Есть (можно опираться)

| Блок | Статус | Где |
|------|--------|-----|
| Цель, scope, MVP-критерии | Готово | план проекта |
| Рынок + боли клиентов | Готово | `market-analysis.md` |
| Стек Django/DRF + React | Готово | `stack-decision.md` |
| SEO URL + 301 + BV ЧПУ | Готово | `seo-url-migration.md`, seed CSV |
| Infra reg.ru VPS/DNS + почта Яндекс 360 | Зафиксировано | `infra-reg-ru.md` |
| Детализация боль→фича→тест | Готово | `plan-detail-mvp.md` |
| Poetry env + Django skeleton | Есть | `backend/` |
| Vite React scaffold | Есть | `frontend/` |
| Compose db/redis (local) | Есть | `docker-compose.yml` |
| Данные каталога (~39 SKU) | Есть | `../hoocon/data/` |
| UX-прототипы B2B | Есть | `../hoocon/docs/прототипы/` |
| Бренд (красный #dc1313, лого) | Есть | прототипы + live hoocon.ru |

### Нет / слабо (закрыть до или в ходе итераций)

| Пробел | Риск | Когда закрыть |
|--------|------|----------------|
| Формальная **дизайн-система** в `hoocon-cms` (tokens, шрифты) | Разъезд UI | До итерации 4 (док ниже = канон) |
| Полный инвентарь **PDF/фото** по SKU | Карточки без файлов | ETL итерация 2 + гейты качества |
| Схема атрибутов (момент, В, сигнал…) как словарь | Кривые фильтры | Итерация 1 + [data-quality-etl.md](data-quality-etl.md) |
| Контент статей/новостей для импорта | Пустые `/statyi` | Итерация 3; тексты **не** as-is с Tilda |
| VPS reg.ru + DNS + SMTP 360 в бою | Не блокер кода | Итерация 5 |
| Docker Desktop локально | Не поднять Postgres | Поднять Postgres (FTS/GIN). `USE_SQLITE` — не для полного migrate |
| Утверждённый макет mobile sticky CTA | Мелкие правки | Итерация 4 (есть в прототипе) |
| Remote GitHub private | Процесс | По команде |

**Вывод:** для старта **бэкенд-итерации 1** материалов достаточно.
Для публичного фронта канон UX — прототипы `../hoocon` + этот документ;
не начинать «с белого листа» и не копировать Tilda e-com.

---

## 2. Как строим backend (архитектура)

### 2.1 Слои (как LMS + БЗ)

```
nginx (prod) → Django (gunicorn)
                 ├─ Admin (staff write)
                 ├─ DRF public read API
                 ├─ spa_index_view (SEO head)
                 ├─ services/ (бизнес-логика, не в views)
                 └─ Celery → SMTP Яндекс 360
Postgres ← catalog / content / leads / redirects
Redis ← Celery broker
```

Правила БЗ: сервисный слой, TDD, типы PEP 585/604, без секретов в git,
длина строки ≤ 119.

### 2.2 Apps и ответственность

| App | Модели / роль | Связь с болью HVAC |
|-----|---------------|--------------------|
| `catalog` | Category, Product, SKU, Attribute*, ProductFile, price | Фильтры, ТТХ, PDF |
| `content` | Page, Article, News | E-E-A-T, статьи |
| `leads` | Lead (RFQ / consult / replace) | Заявка вместо корзины |
| `search` | FTS helpers / signals | Глобальный поиск |
| `redirects` | Redirect (from→to, 301) | SEO / tproduct |
| `config` | settings, Celery, spa SEO, SiteSettings | Флаг цен, SMTP |

`media`: файлы на диск VPS (`MEDIA_ROOT`); позже S3 — не v1.

### 2.3 API (публичное)

- `GET /api/catalog/categories/`
- `GET /api/catalog/skus/?torque=&voltage=&spring=&q=`
- `GET /api/catalog/skus/{slug}/` — ТТХ, файлы, аналоги (поле задел)
- `GET /api/content/pages/{slug}/`, articles, news
- `GET /api/search/?q=`
- `POST /api/leads/` — RFQ (throttle + honeypot)
- `GET /api/schema/`, `/api/docs/` — spectacular

Цены в сериализаторе только если `show_prices_on_site`; иначе поле
отсутствует или `null` + флаг `price_on_request: true`.

### 2.4 Порядок реализации (не менять без нужды)

1. Модели catalog + Redirect + тесты  
2. Admin + API list/detail/filters  
3. ETL весь каталог (slug из sitemap / seed)  
4. FTS + ProductFile  
5. content + leads + Celery mail  
6. Frontend по прототипу + spa head  
7. nginx 301 + reg.ru  

---

## 3. Успех и боль HVAC → продуктовые решения

| Что работает у лидеров | Боль / антипаттерн | Наше решение |
|------------------------|--------------------|--------------|
| Belimo: «Продукция» + «Расчёт и выбор» + каталоги PDF | Сложный подбор без инструмента | Фасеты P0; подбор/замена P1 |
| Belimo/OEM: видимое меню, поиск по артикулу | Бургер + Cart на Tilda | Desktop nav + поиск; **без корзины** |
| Дилеры: таблицы аналогов Belimo | Клиент уходит к дилеру | AnalogMap + страница позже; поля в SKU с v1 |
| Dastech: серии по применению + кейсы РФ | Слабый E-E-A-T у Hoocon | Категории по применению; блок доверия в UI |
| Download center | PDF «где-то в тексте» | ProductFile + блок «Документы» на PDP |
| RFQ / КП по запросу | Корзина без цены | CTA «Запрос КП»; список спецификации (не cart) |
| Склад / срок | Пустой оффер | Якоря: склад Москва, SLA ответа, CE/UL/EAC |

Не копируем: устаревший «портальный» вид belimo.ru (перегруз новостями);
вебшоп Belimo global; открытый прайс, если политика — скрытые цены.

---

## 4. UX / дизайн B2B — выбранное направление

### 4.1 Канон

**База:** прототипы `../hoocon/docs/прототипы/` + палитра
`prototip-hoocon-shared.css`.  
**Референсы паттернов (не визуальный клон):** Belimo.com / Danfoss /
Siemens Building (см. `РЕФЕРЕНСЫ_OVK_B2B.md`) — структура и IA;
цвет и логотип — **только Hoocon**.

### 4.2 Визуальный язык (industrial B2B, 2026)

| Токен | Значение | Смысл |
|-------|----------|--------|
| Brand | `#dc1313` / `#b01010` | HOOCON red — hero-level в логотипе |
| Текст | `#333` / `#555` / `#858585` | Инженерная читаемость |
| Фон | `#f2f2f2` page, `#fff` поверхности | «Цех / каталог», не lifestyle |
| Masthead / footer | `#2d2d2d` / `#1a1a1a` | Как у OEM (Danfoss-like utility) |
| Радиус | `8px` | Сдержанно; не pill-ui |
| Тень | лёгкая `0 4px 24px rgba(0,0,0,.06)` | Без glow / glassmorphism |
| UI text | **IBM Plex Sans** | Инженерный B2B; Montserrat — display/бренд |
| Display | Montserrat | Заголовки, логотип |

Тренды, которые сознательно **не** берём: purple gradients, cream+serif
terracotta, dark-mode first, emoji, rounded-full pills, multi-layer neon.

Тренды, которые **берём**: чёткая иерархия; фото продукта edge-to-edge
в hero; attribute-first карточки; sticky CTA на mobile; focus-visible;
skip-link; performance budget CWV.

### 4.3 UX-паттерны экранов

1. **Шапка:** utility (телефон, email) + логотип + **видимое** меню +
   поиск по артикулу. Без Wishlist/Cart; **«Список запроса»**
   (спецификация → RFQ) — как в прототипе.
2. **Главная:** бренд + один оффер + CTA «Каталог» / «Запрос инженеру»;
   3 якоря доверия; вход по направлениям (воздух / ПБ / дым / краны);
   полоса ресурсов (PDF, сертификаты, партнёры); FAQ.
3. **Каталог:** фильтры слева (chips) ↔ query string; сетка SKU с
   ключевыми ТТХ; пагинация ссылками.
4. **Карточка (PDP):** фото + таблица атрибутов + документы + аналоги +
   «Запрос КП» (SLA в подписи).
5. **Контент:** статьи/новости как у OEM support, не блог-lifestyle.
   Числа, доли, сроки, KPI — **графики и дашборды** (HTML/CSS-классы,
   `cms-body-charts.css`),
   не стена текста. Референс: `/zavod`.

### 4.4 Соответствие «направлению» HVAC

- Визуально: металл/продукт, нейтральный фон, акцент бренда — как у
  field-device OEM, не маркетплейс.
- Поведенчески: инженерный путь «параметр → документ → заявка».
- Современность: скорость, a11y, SEO-гибрид, чистые URL — сильнее
  типичного дилерского сайта 2010-х (пример: перегруженный belimo.ru),
  при этом проще и локальнее global Belimo.

### 4.5 Перенос в React

- CSS variables из §4.2 → `frontend/src/styles/tokens.css`
  (см. также [design-system.md](design-system.md)).
- Компоненты layout по прототипу (Header, Filters, SkuCard, PdpBuy).
- Контент hero — реальные фото продукции (из media ETL), не абстрактный
  градиент.

---

## 5. Решение «готовы ли стартовать код»

| Вопрос | Ответ |
|--------|-------|
| Понятны боли и дифференциация? | Да |
| Понятен backend? | Да (§2) |
| Понятен UX/дизайн? | Да (§4), канон = прототипы Hoocon |
| Весь каталог в scope? | Да (~39 SKU) |
| SEO URL? | Да |
| Prod reg.ru VPS/DNS + Яндекс 360 почта? | Да |
| Блокер до итерации 1? | Нет (Docker/Postgres — удобство, не стоп) |

Рекомендация: после вашего «ок» по этому документу — **итерация 1**
(модели catalog + Redirect + тесты), параллельно завести `tokens.css`
из §4.2 без полной вёрстки всех страниц.

---

## 6. Зафиксированные уточнения (2026-07-19)

| Вопрос | Решение |
|--------|---------|
| Список запроса | Как в прототипе (не корзина); RFQ с карточки обязателен |
| Шрифт UI | **IBM Plex Sans** + Montserrat (бренд) |
| VPS reg.ru | К итерации 5 / cutover; разработка локально |

Качество переноса данных: **не копируем ошибки Tilda** —
[data-quality-etl.md](data-quality-etl.md).  
Безопасность с итерации 1: [security-baseline.md](security-baseline.md)
(OWASP 2025, БЗ модуль безопасности).

Рекомендация: старт **итерации 1** (модели + Redirect + validate ETL).