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
  (BR-ML только для DA…FU); выбор попадает в текст заявки.

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
