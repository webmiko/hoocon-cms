# QA: карточки товара DA\* (DAMU)

Ручная проверка. Находки копили, затем чинили пакетно по семейству DA\*MU.

Статус: **исправлено локально** (2026-07-29); на прод — после деплоя + refill Belimo / ensure signals.

Локалка: http://127.0.0.1:5173/

---

## Находки

| # | Где | Что не так | Scope | Приоритет | Статус |
|---|-----|------------|-------|-----------|--------|
| 1 | DA2MU / DA4MU — ТТХ «Упр. сигнал Y …» | Две одинаковые карточки | Все modulating DA\*MU (28 SKU) | high | **fixed** |
| 2 | DA\*MU -S — вкладка «Инструкция» | Не было настройки вспом. переключателя (только stub) | Все DA\*MU -AS/-DS | high | **fixed** |
| 3 | DA4MU D vs DS — аналог Belimo | Один и тот же код (часто `…-S` у D) | Все DA\*MU D/DS с lone `…-S` в карточке | high | **fixed** (кроме DA2MU, см. ниже) |

### #1 Дубль «Упр. сигнал Y»

- Причина: в EAV жили и `control-signal` («Упр. сигнал Y»), и legacy `control-signal-y` («Управляющий сигнал Y») с одним value; dedupe ключил по имени → оба проходили; FE `compactCardSpecName` делал их визуально одинаковыми.
- Фикс:
  - `catalog/facets/dedupe.py` — slug-bucket + нормализация имён Y/U;
  - `ensure_modulating_signal_attributes` — удаляет legacy alias после записи канона;
  - локально прогнан ensure по DA\*MU (снесено 56 alias-строк).

### #2 Инструкция: настройка -S

- Причина: `instructions_for_damu_sku` писал stub «по заводской таблице».
- Фикс: таблица клемм 21–23 (и b/24–26 при 2 группах) + DIP Y/U для modulating -AS; то же в `SERIES_INSTRUCTIONS`.

### #3 Belimo D vs DS

- Причина: в `analogs_text` для D/DS одна строка `LM24A-S`; `_filter_codes_by_aux` не трогал одиночный код.
- Фикс: для non-aux SKU одиночный `…-S` → strip до base; refill `analog_belimo_code` локально (8 SKU: DA4/6/8/16/24/32 …-D).
- **Исключение DA2MU:** D и DS оба `CM24-L/R` / `CM230-L/R` — у Belimo CM нет пары без/с `-S` в карточке. Оставить как есть, пока не появится отдельный артикул.

---

## Порядок исправлений (сделано)

1. Дубль Y (#1) — dedupe + cleanup alias.
2. Инструкция aux (#2) — `series_copy_damu`.
3. Belimo D/DS (#3) — `_filter_codes_by_aux` + refill.

## После деплоя на прод

```bash
poetry run python manage.py normalize_tech_copy   # ensure modulating signals / drop aliases
poetry run python manage.py fill_belimo_analogs --force
# либо точечно по DA*MU
```

(точные флаги команд — сверить с `--help` на момент деплоя.)
