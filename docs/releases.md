# Версии релизов Hoocon CMS (админка + фронт)

> Канон SemVer: `backend/config/release.py` (`RELEASE_VERSION`,
> `RELEASE_CHANNEL`). Синхронно: `backend/pyproject.toml`,
> `frontend/package.json`, OpenAPI / `/api/health/`.

## Схема (beta → GA)

| Событие | Действие | Пример |
|---------|----------|--------|
| Новая **фича** (Admin или фронт) | PATCH `0.0.N` → `0.0.N+1` (до `0.0.9`) | `0.0.1` → `0.0.2` |
| Косметика / docs / тесты без UX | Версию **не** поднимать | — |
| **Глобальное** обновление (GA / breaking) | `1.0.0`, канал `""` | `v1.0.0` |
| Статус до GA | `RELEASE_CHANNEL = "beta"` | `v0.0.3 beta` |

Отображение: **`v{VERSION} {channel}`** (например `v0.0.3 beta`).
После `0.0.9` следующая фича в beta — согласовать MINOR (`0.1.0`) или
переход к `1.0.0`.

**Не** версионировать под оплату/корзину — их нет в v1.

## Где видно

- Админка Unfold: бейдж окружения (`ENVIRONMENT`).
- Сайт: подпись в футере.
- `GET /api/health/` → `version` + `channel`.

## Чеклист при фиче

1. Поднять `RELEASE_VERSION` в `config/release.py`.
2. Скопировать ту же строку в `pyproject.toml` и `frontend/package.json`
   (+ `frontend/src/release.ts`).
3. Строка в changelog ниже.
4. Коммит темы фичи (атомарно); версию можно тем же коммитом или
   отдельным `Bumped release to v0.0.N beta`.

## Changelog

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
