# Решение по стеку: Hoocon CMS

Дата: 2026-07-19.  
Опора: база знаний (Django/DRF + React SPA) + официальные источники
за пределами БЗ (см. раздел «Вне БЗ»).

---

## 1. Рекомендация (итог)

| Слой | Выбор | Почему |
|------|--------|--------|
| Backend | **Django + DRF** (Py 3.12+) | Стек БЗ и LMS; TDD, сервисный слой |
| БД | **PostgreSQL** | FTS, JSONB для атрибутов SKU |
| CMS-контент | **Django Admin** + **django-unfold** + свои apps | Без Wagtail в v1; UI-стандарт 2026-07-23 |
| Admin UI / цвета | Unfold `COLORS.primary` из brand hex | [admin-standard.md](admin-standard.md); как LMS |
| Опция CMS | **Wagtail** (этап 2) | docs.wagtail.org — editor UX |
| Поиск | Postgres FTS → **Meilisearch** | Простота → фасеты при росте |
| Очереди | **Celery + Redis** | импорт, письма, превью PDF |
| Frontend | **React + TS + Vite** | БЗ / LMS; гибрид SEO |
| Edge | **nginx**, Docker Compose, GitHub Actions | Как LMS |
| Auth админки | Session + CSRF (staff); JWT только для API SPA admin | БЗ: безопасность SPA |

**Не берём в v1:** онлайн-корзину, Stripe/платежи, Next.js (можно позже, если
понадобится полный SSR без гибрида Django).

---

## 2. Почему не «чистый» WordPress / Tilda / headless-only

- Tilda уже ограничивает фильтры, поиск и модель SKU (`../hoocon` аудит).
- WordPress PHP — вне вашего основного стека и БЗ.
- Headless-only без Django admin усложняет B2B-редакторов на старте.

---

## 3. Backend: детализация

### Модули (apps)

1. `catalog` — Category, Product, SKU, Attribute, AttributeValue, ProductFile.
2. `content` — Page, Article, News (или Wagtail pages на этапе 2).
3. `leads` — Inquiry / RFQ / «замена привода» (без оплаты).
4. `search` — индексация каталога + статей.
5. `media` — файлы datasheet, изображения (S3/локально).
6. `accounts` — staff/роли (контент / каталог / заявки).

### API

- Публичное read-only API каталога и контента.
- Staff API / Django admin для записи.
- OpenAPI (drf-spectacular) — как в LMS.

### Поиск

Этап A: `django.contrib.postgres.search` (офиц. Django docs).  
Этап B: Meilisearch ([docs.meilisearch.com](https://www.meilisearch.com/docs)) —
фасеты, опечатки, скорость для большого каталога.

---

## 4. Frontend: современные подходы (2026)

Из БЗ (`ВЕБ-РАЗРАБОТКА-Кастомный-стек`):

- React + TS + Vite, code splitting, performance budget;
- accessibility WCAG 2.2 AA;
- SEO: уникальные title/description в **исходном HTML**, canonical, JSON-LD;
- CSP, без ослабления ради SEO.

Практика публичного B2B-каталога:

- SSR/гибрид для карточек и статей (индексация);
- клиентские фильтры с URL state (`?torque=10&voltage=230`);
- скелетоны, пагинация/infinite осторожно для SEO (лучше page links).

Официальные ориентиры вне БЗ:

- [React docs](https://react.dev/) — Server Components опционально позже;
- [Vite](https://vite.dev/) — tooling;
- [web.dev](https://web.dev/) — CWV (LCP/INP/CLS).

Альтернатива на будущее: **Next.js** или **Astro** для маркетинговых страниц —
только если гибрид Django+SPA упрётся в SEO/DX. В v1 остаёмся на стеке БЗ.

---

## 5. Wagtail vs свои apps (решение)

| | Wagtail | Свои apps (v1) |
|--|---------|----------------|
| Редактор | отличный StreamField | Django Admin + позже React admin |
| Каталог SKU | неудобен как «товар» | идеально моделями |
| Сложность | +ещё одна система | проще старт |
| API | Wagtail API | DRF единообразно |

**v1:** свои apps + **Django Admin** + **django-unfold** (бренд-цвета).  
**v2:** Wagtail только для статей/лендингов — если Admin станет узким местом
для редакторов ([docs.wagtail.org](https://docs.wagtail.org/)).
См. [admin-standard.md](admin-standard.md).

### Цены

- Поля цены в каталоге обязательны для внутреннего учёта / КП.
- Публичный показ: **выключен** по умолчанию (`show_prices_on_site=False`).
- Включение — настройка сайта в Admin, без редеплоя логики.

### Git и выкладка

- Репозиторий на GitHub — **private**.
- Разработка и запуск — локально (Docker Compose).
- Публичный деплой — отдельный этап после готовности MVP.
- **Prod-хост:** VPS reg.ru; домен и почта там же
  ([infra-reg-ru.md](infra-reg-ru.md)). SMTP заявок — ящики reg.ru,
  не внешний ESP по умолчанию.

---

## 6. Соответствие Python / инструкции БЗ

- Python **3.12–3.13** → ЕДИНАЯ_ИНСТРУКЦИЯ **v2.0**.
- Poetry / uv, Ruff, mypy, pytest — как в ПРОМПТ-ДЛЯ-ПРОЕКТОВ.
- Строка кода/плана ≤ 119 символов.

---

## 7. Вне БЗ — источники, которые стоит перенести в базу

См. [kb-update-proposals.md](kb-update-proposals.md):

- Wagtail vs django CMS (офиц. docs);
- Postgres full-text search (Django docs);
- Meilisearch для faceted product search;
- B2B RFQ-паттерн (без e-commerce).
