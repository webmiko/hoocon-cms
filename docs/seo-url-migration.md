# SEO: сохранение URL и редиректы (Tilda → Hoocon CMS)

Дата: 2026-07-19 (обновлено 2026-07-23)  
Правило: **не ломать индексированные URL без 301**.  
Опора БЗ: `ВЕБ-РАЗРАБОТКА-Кастомный-стек/SEO-индексация-SPA.md`
(canonical без trailing slash; nginx 301 дублей; head в исходном HTML).
Title/description для сниппетов: [seo-meta-yandex-google.md](seo-meta-yandex-google.md).

Снимки sitemap: 2026-07-19 (`sitemap.xml` + `sitemap-store.xml`).

### Каталог (канон с 2026-07-23)

| Path | Тип |
|------|-----|
| `/catalog` | весь каталог |
| `/catalog/{category}` | список SKU категории |
| `/catalog/{category}/{sku}` | **карточка SKU** (отдельная страница на каждый артикул) |

Legacy: `/catalog?category=…` → клиентский redirect на `/catalog/{category}`;
плоский `/{sku}` → `/catalog/{category}/{sku}` (SPA) + canonical в SSR head.

---

## 1. Стратегия (зафиксировано)

| Принцип | Решение |
|---------|---------|
| Хорошие ЧПУ из основного sitemap | **Сохранить path как canonical** (`slug` в БД = path без `/`) |
| Tilda `/tproduct/…` | **301** → ЧПУ карточки SKU |
| Опечатки в slug (уже в индексе) | **Исправить canonical** + **301** со старого path |
| Trailing slash, `/index.html` | **301** на канон без `/` (как LMS) |
| Новые посадочные | Новые ЧПУ + внутренние ссылки; старые не трогать |
| Реализация | Поле `slug` + таблица `Redirect` + nginx map на VPS |

Предпочтение: **правильный ЧПУ** как canonical; старый (с опечаткой)
адрес не удаляем — отдаём **301** на канон
([redirects-slug-typo-seed.csv](redirects-slug-typo-seed.csv)).

---

## 2. Инвентарь текущего сайта

### 2.1 Основной `sitemap.xml` → канон на новом сайте

| Path | Тип в CMS | Canonical на новом сайте |
|------|-----------|--------------------------|
| `/` | home | `/` |
| `/catalog` | catalog list | `/catalog` |
| `/company` | page | `/company` |
| `/zavod` | page | `/zavod` (завод Ningbo Hoocon · OEM) |
| `/gde-kupit` | page | `/gde-kupit` |
| `/statyi` | article list | `/statyi` |
| `/news` | news list | `/news` |
| `/sale` | page / promo | `/sale` или 301→`/catalog` (решить при ETL) |
| `/oferta` | legal | `/oferta` |
| `/privacy-policy` | legal | `/privacy-policy` |
| `/terms` | legal | `/terms` |
| `/sitemap` | html map | `/sitemap` или 301→`/sitemap.xml` |
| `/elektroprivody-dlya-zaslonok-ventilyatsii` | landing | тот же path (Page/Article) |
| `/privod-…` (SKU ниже) | SKU detail | **исправленный** ЧПУ (см. список) |

SKU ЧПУ (канон; опечатки Tilda → 301):

```
privod-dimoudaleniya-10nm
privod-dimoudaleniya-15nm
privod-dimoudaleniya-30nm
privod-protivopozharniy-3nm          ← было protivipozharniy
privod-protivopozharniy-5nm
privod-protivopozharniy-10nm
privod-protivopozharniy-15nm
privod-protivopozharniy-20nm
privod-vozdushniy-bez-pruzhini-damu-2nm
privod-vozdushniy-bez-pruzhini-damu-4nm
privod-vozdushniy-bez-pruzhini-damu-6nm
privod-vozdushniy-bez-pruzhini-damu-8nm
privod-vozdushniy-bez-pruzhini-damu-16nm
privod-vozdushniy-bez-pruzhini-damu-24nm
privod-vozdushniy-bez-pruzhini-damu-32nm
privod-vozdushniy-bez-pruzhini-uskorenniy-hva-q-5nm  ← было bezpruzhini
privod-vozdushniy-hva-5nm
privod-vozdushniy-hvd-5nm
privod-vozdushniy-hvd-10nm
privod-vozdushniy-hvd-20nm
privod-vozdushniy-pruzhina-dafu-3nm
privod-vozdushniy-pruzhina-dafu-5nm
privod-vozdushniy-pruzhina-dafu-10nm
privod-vozdushniy-pruzhina-dafu-15nm
privod-vozdushniy-pruzhina-dafu-20nm
```

**301 с опечаток:** [redirects-slug-typo-seed.csv](redirects-slug-typo-seed.csv)
(`import_redirects` + `RedirectMiddleware` + nginx map).

### 2.2 `sitemap-store.xml` — Tilda Store (нужны 301)

**Шаблон ЧПУ шаровых кранов (утверждено 2026-07-19):**

```
/sharovoy-kran-{артикул_lowercase}
```

Пример: BV215 → `/sharovoy-kran-bv215`.

Часть товаров есть только как `/tproduct/<id>-<slug>`. Для каждого —
канонический ЧПУ + **301**. Полная карта-seed:
[redirects-tproduct-seed.csv](redirects-tproduct-seed.csv).

| Старый URL (Tilda) | Целевой ЧПУ |
|--------------------|-------------|
| `/tproduct/…-bv215-…` | `/sharovoy-kran-bv215` |
| `/tproduct/…-bv220-…` | `/sharovoy-kran-bv220` |
| … BV225…BV350 | `/sharovoy-kran-bv{NNN}` |
| `/tproduct/…-hvd-40q-…` | `/privod-vozdushniy-hvd-40q` |
| `/tproduct/…-da8mqu-…` | `/privod-vozdushniy-da8mqu-8nm` |

На cutover перепроверить sitemap-store и дописать новые строки в CSV
→ загрузка в `Redirect`.

### 2.3 Технические / мусорные URL Tilda

| Pattern | Действие |
|---------|----------|
| `/pageNNNN.html` | 301 на ближайший смысловой URL или `/` |
| `/tilda/*`, form endpoints | 410 или 404; Disallow в robots |
| Дубли с `www` / http | 301 → `https://hoocon.ru` без www |

---

## 3. Модель данных (для реализации)

На SKU / Page / Article:

- `slug` — **канонический** path-сегмент (как в индексе).
- опционально `legacy_slugs: list[str]` — доп. алиасы с 301 на canonical.

Отдельная сущность `Redirect`:

- `from_path` (unique), `to_path`, `status_code` (301/302), `is_active`.
- Админка staff; сиды из CSV при ETL.
- Отдача: nginx `map` **или** Django middleware до SPA
  (предпочтительно nginx на VPS — быстрее, как LMS).

Фильтры каталога: query string (`/catalog?torque=5&voltage=230`) —
**не** отдельные индексируемые URL без `canonical` на `/catalog`
(или на посадочную, если сознательно заведём landing).

---

## 4. nginx / SPA (reg.ru VPS)

Минимум (из БЗ + LMS):

```
# псевдо-правила
/path/        → 301 /path
/index.html   → 301 /
http / www    → 301 https://hoocon.ru
# map из Redirect / файла redirects.map
```

Публичные маршруты React/Django должны **регистрировать те же paths**,
что и старый сайт. Server-side head (`spa_index_view`) — по `slug` из БД.

Тесты (обязать в итерации 5):

- каждый path из инвентаря §2.1 → **200** + canonical совпадает;
- каждый `/tproduct/…` из карты → **301** на целевой ЧПУ;
- trailing slash → 301;
- pytest по аналогии с `tests/test_nginx_spa_canonical_urls.py` (LMS).

---

## 5. Cutover-чеклист SEO

- [ ] Выгрузка актуальных sitemap.xml + sitemap-store.xml в день релиза
- [ ] CSV редиректов залит; выборочный curl 20 URL
- [ ] Новый `sitemap.xml` только с канонами (без `/tproduct/`)
- [ ] GSC / Яндекс.Вебмастер: смена sitemap, мониторинг 404
- [ ] Метрика: цели на новых URL; сверка трафика 2–4 недели
- [ ] Параллельный запуск: низкий TTL DNS; rollback = DNS обратно на Tilda

---

## 6. Связь с болями рынка

Сохранение URL защищает уже заработанные позиции по SKU и лендингам
(кластеры из `../hoocon/docs/SEO_ЗАПРОСЫ_100_КЛЮЧЕВЫХ.md`).
Новые страницы (`/analog-belimo`, посадочная по кранам) — **добавляем**,
не заменяя старые path без 301.

Связано: [market-analysis.md](market-analysis.md),
[infra-reg-ru.md](infra-reg-ru.md), [ПЛАН-ПРОЕКТА.md](../ПЛАН-ПРОЕКТА.md).
