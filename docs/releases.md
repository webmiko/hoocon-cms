# Версии релизов Hoocon CMS (админка + фронт)

> Канон: `backend/config/release.py` (`RELEASE_VERSION`,
> `RELEASE_CHANNEL`). Синхронно: `backend/pyproject.toml`,
> `frontend/package.json`, `frontend/src/release.ts`, OpenAPI /
> `/api/health/`.

## Две эпохи

### 1. Beta (до GA) — три числа + канал

| Событие | Действие | Пример |
|---------|----------|--------|
| Новая **фича** | Поднять по схеме beta (`0.0.x` → `0.1.0` …) | `0.0.9` → `0.1.0` |
| Косметика / docs / тесты без UX | Версию **не** поднимать | — |
| **GA** (явная команда) | `RELEASE_VERSION = "1.0"`, канал `""` | `v1.0` |
| Статус до GA | `RELEASE_CHANNEL = "beta"` | `v0.1.0 beta` |

Отображение beta: **`v{VERSION} beta`** (например `v0.1.0 beta`).

Первый публичный GA в UI — **`v1.0`** (не `v1.0.0`). Исторически точка
перехода называется «как v1.0.0» в SemVer; в продукте сразу два числа.

### 2. После GA — два числа `vMAJOR.MINOR`

Формат отображения и канона: **`v1.0`**, **`v1.1`**, … **`v1.99`**.

| Событие | Действие | Пример |
|---------|----------|--------|
| Новая **фича** | Авто: **MINOR** `+1` (счётчик **0…99**) | `1.0` → `1.1` |
| Косметика / docs / тесты | Версию **не** поднимать | — |
| **MAJOR** (breaking / новая эпоха) | **Только по явной команде** пользователя | `1.17` → `2.0` |
| MINOR дошёл до **99** | Не поднимать MAJOR сам; спросить пользователя | — |

- **MINOR** (вторая цифра) — меняется агентом при каждой новой фиче, как
  раньше PATCH/MINOR в beta.
- **MAJOR** (первая цифра) — **никогда** автоматически; только если
  пользователь явно сказал (например «подними major», «v2», «новая эпоха»).
- Диапазон MINOR по умолчанию: **0–99**. Иные пределы — только по явному
  указанию.

`RELEASE_CHANNEL` после GA — пустая строка `""`.

Для `pyproject.toml` / `package.json` (нужен SemVer `X.Y.Z`) хранить
`MAJOR.MINOR.0` (патч всегда `0`), а в `RELEASE_VERSION` и UI — `MAJOR.MINOR`.

**Не** версионировать под оплату/корзину — их нет в v1.

## Где видно

- Админка Unfold: бейдж окружения (`ENVIRONMENT`).
- Сайт: подпись в футере.
- `GET /api/health/` → `version` + `channel`.

## Чеклист при фиче

1. Поднять `RELEASE_VERSION` в `config/release.py` (по эпохе выше).
2. Синхронизировать `pyproject.toml`, `frontend/package.json`,
   `frontend/src/release.ts` (после GA: npm/poetry = `{MAJOR}.{MINOR}.0`).
3. Строка в changelog ниже.
4. Коммит темы фичи (атомарно); версию — тем же коммитом или отдельным
   `Bumped release to v…` по просьбе / `чкд`.

## Changelog

### v0.1.19 beta — 2026-08-06

- Новость «Анонс: адаптеры BR-M и BR-ML» в seed и миграции (обложка с BR-M).
- RU-мануалы: case-insensitive поиск PDF при UPPER-именах в `_инструкции-pdf/RU`.

### v0.1.18 beta — 2026-08-06

- Заявки с сайта: режимы распределения менеджерам (выкл / назначение + sales@ /
  назначение + письмо на email менеджера) в Интеграциях.

### v0.1.17 beta — 2026-08-05

- BR-ML: совместимость только с DA5FU (24/230 В); технички PDF кронштейна/штоков.
- 8100 3-ходовые: инструкция направления потока + схема в галерее.
- 8100 издания: фото расходного диска Kvs в галерее SKU.

### v0.1.16 beta — 2026-08-05

- Home: server-rendered hero shell (H1/CTA + LCP WebP preload) in Django SPA
  HTML so FCP/LCP can fire before React mounts.

### v0.1.15 beta — 2026-08-04

- Home: below-fold sections mount near the viewport (lazy carousels + deferred
  categories/novinki API) to cut first-screen JS and network payload.

### v0.1.14 beta — 2026-08-04

- Catalog/mobile: lightweight `ProductImage.image_card` WebP (≤720px) for
  list tiles; full hero stays on SKU detail. Backfill:
  `manage.py generate_product_image_cards`.
- a11y: carousel tracks keep `role="list"` under flex/grid; region landmark
  moved off `<ul>`.

### v0.1.13 beta — 2026-07-30

- Admin: passwordless Email OTP login when `ADMIN_EMAIL_OTP_ENABLED=true`
  (username/email → 6-digit code); classic password when flag is off.

### v0.1.12 beta — 2026-07-30

- H8205: DN-ascending catalog order; Instructions tab from wiring catalog text.
- Catalog heroes: H81/H8205 + DA/SA on shared canvas; real overall dimensions for
  DAFU/SAFU/SAMU/HVDF; article/news cover folders match canonical slugs
  (`aquatherm-2025` + 301s).

### v0.1.11 beta — 2026-07-30

- Catalog heroes: shared portrait canvas sizing for brass DN and HV Nm; HVD-…F
  photos centered after SAF72 pad trim; FE skips double scale on baked packs.

### v0.1.10 beta — 2026-07-29

- Home: Novinki CSS scroll-snap carousel; frosted captions on object cases.
- Related articles: Safari/PWA slide transitions; local `sync-db-from-vps`.

### v0.1.9 beta — 2026-07-29

- SEO: SSR `og:image` для PDP через family gallery fallback (как на карточке/PDP).

### v0.1.8 beta — 2026-07-29

- Аналитика: цели `lead_submit` / SPA hits; Metrika `73321399`, GA4 `G-DLRV7BZ5JP`;
  отложенный старт счётчиков 3 с после согласия на cookie.
- SEO: уникальные description категорий, OG-картинки PDP/статей, CMS `h1`→`h2`,
  meta `yandex-verification`.
- Главная: блок «На объектах»; единый CTA «Запросить КП».

### v0.1.7 beta — 2026-07-29

- Фото: единый wash (светло-серый / графит); масштаб по Нм 75–100% с компенсацией кропа.
- Главная: превью «с пружиной» на DA5FU; герои DA10/15FU A/AS из media-webp.

### v0.1.6 beta — 2026-07-29

- Каталог: Y/U на карточках A/AS; фильтры «в наличии» / «новинки» над категориями.
- Media-webp: DA/SA герои, montage extras; wash cutout на карточках и PDP.
- Каталог gaps: DAMQU 5/10/20, SA7MU, bare HVD-40; сняты HVA-P и DAEU (не РФ).

### v0.1.5 beta — 2026-07-28

- Новинки на главной: компактные teaser-карточки в карусели; направления — 4 колонки.
- Фото cutout: графитовый wash air и боковой inset; восстановление lone unpublished hero.
- ETL: `attach_hv_media_webp` для оптимизированных HV-героев из media-webp.

### v0.1.4 beta — 2026-07-28

- Новинки: `first_published_at` у SKU, бейдж «Новое», фильтр `?new=1`,
  блок на главной; stamp HV-волны для витрины.

### v0.1.3 beta — 2026-07-28

- HVA: линейки 5/10/20/40 и ускоренные Q — seed, ТТХ, локальные фото и PDF.
- HVD-Q (5–40Q), HVA-P (пружина 5/10/15P) и конденсаторные HV*QX —
  карточки, ТТХ; HVD — медиа из HV seria.
- План статей: ссылки на единый веб-промпт §6 (тексты) и §8 (SEO).

### v0.1.2 beta — 2026-07-28

- Сравнение: дозаполнение «—» из EAV при усечённых highlights; без ложных
  строк legacy Y/U; артикулы UPPERCASE.
- DAMU: длина кабеля и сечение провода в shared ТТХ; аудит пробелов
  `audit_series_attr_gaps` по DA/SA/HV.
- Копирайт: ОВК / ПБ / ТТХ расшифрованы в chrome и SEO; контраст brand CTA ≥ AA.

### v0.1.1 beta — 2026-07-28

- Сравнение на mobile: карточки характеристик без горизонтального скролла.
- Аналоги Belimo: разделены редакции AS/DS и DS/DST (control / thermal).

### v0.1.0 beta — 2026-07-27

- Поиск: подсветка совпадений запроса (слово / фраза) в заголовке и
  сниппете результатов для быстрого нахождения места в тексте.
- Поиск: сниппеты статей/новостей/страниц — plain text без HTML-тегов.
- Политика релизов: после GA — `vMAJOR.MINOR` (MINOR 0–99 по фичам;
  MAJOR только по явной команде).

### v0.0.9 beta — 2026-07-24

- DAMU (DA*) и SAMU (SA*): в каталоге одна плитка на Nm-линейку, издания
  на PDP через picker (V / управление; у SA отдельно DS и DST).
- Шаблоны карточек серий: [series-card-templates.md](series-card-templates.md).

### v0.0.8 beta — 2026-07-24

- Admin: загрузка остатков из выгрузки 1С; на карточках и PDP лейбл
  «Есть / Нет в наличии» (`in_stock`, без сырого qty).
- Комплекты H81 (фото/габариты из каталога) и категория «Комплекты»;
  фасет «Материал корпуса»; термодатчик Нет/SAF72 для дымоудаления.

### v0.0.7 beta — 2026-07-24

- Страница завода `/zavod`: Ningbo Hoocon Automation, OEM / private label
  и сотрудничество напрямую с заводом через ООО «Хогон».

### v0.0.6 beta — 2026-07-23

- Nested catalog SKU URLs: `/catalog/{category}/{sku}` (one page per SKU);
  legacy `?category=` and flat `/{sku}` redirect to the nested path.
- Catalog cards: photo-edge wash, one card per row, gradient hover border;
  no divider between photo and copy (list + PDP hero).

### v0.0.5 beta — 2026-07-21

- Карточки приводов: единый набор ТТХ (момент, напряжение, управление,
  площадь, вспом. переключатель; Y/U у пропорциональных), включая «Нет».
- Парсинг суффикса ``-dst`` для управления/aux и согласованный Belimo-фильтр.

### v0.0.4 beta — 2026-07-21

- Шаровые краны: в RFQ можно добавить совместимый привод и кронштейн
  (BR-ML только для DA5FU); выбор попадает в текст заявки.

### v0.0.3 beta — 2026-07-21

- Admin sidebar: узкий icon rail на desktop, hover-peek, мобильный overlay,
  sticky header.

### v0.0.2 beta — 2026-07-21

- Staff Groups: Админ / Менеджер / Аналитик (`sync_staff_groups`).
- Lint английских слов в русской Admin UI + переводы подписей.
- ETL: truncate AttributeValue по `max_length`, N+1 enrich cards,
  thermal Belimo primary без не-thermal fallback.
- Нумерация релизов Admin/фронт (`docs/releases.md`).

### v0.0.1 beta — 2026-07-20

- Базовый CMS-каталог, RFQ, CRM Admin, публичный SPA (итерации 1–4).
