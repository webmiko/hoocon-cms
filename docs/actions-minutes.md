# Счётчик минут GitHub Actions (бесплатный деплой)

Private Free: **2000 мин/мес** на GitHub-hosted runners.
Скрипт делит бюджет на **4 недели по 500 мин**, чтобы не сжечь квоту
в начале месяца.

```bash
./scripts/actions-minutes.py            # отчёт
./scripts/actions-minutes.py --refresh  # пересчитать по runs
./scripts/actions-minutes.py --set-used 420   # факт из UI Billing
./scripts/actions-minutes.py --json
```

## Как считается

| Поле | Смысл |
|------|--------|
| Месяц | 2000 мин, сброс 1-го числа (календарный месяц UTC) |
| Неделя 1…4 | дни 1–7 / 8–14 / 15–21 / 22–конец месяца; лимит **500** |
| Оценка | сумма длительностей job'ов CI (каждая job ↑ до целой минуты) |
| Ручной факт | `--set-used` из **Settings → Billing → Actions** (точнее API) |

Кэш: `.local/actions-minutes.json` (в git не попадает).

## Темп

К концу недели N равномерный потолок = `N × 500`.
Если месяц уже выше — скрипт предупреждает «темп выше плана».

Один полный CI (check → build → deploy) обычно **~4–10 мин**
после оптимизации pipeline (см. `.github/workflows/ci.yml`).

| Событие | Jobs | Минут (оценка) |
|---------|------|----------------|
| PR | check | ~3–5 |
| push `develop` | check + build | ~5–8 |
| push `main` | check + build + deploy | ~6–10 |
| push только `docs/**`, `*.md` | — (workflow не стартует) | 0 |

При лимите 500/нед это заметно больше прогонов, чем при старой
цепочке test→lint→build→deploy на каждый push.

## Связь с деплоем

Канон после оптимизации CI:

- **Автодеплой:** push в `main` → Actions → VPS
- **develop:** check + build (образ в GHCR), без deploy — выкладка
  `./scripts/deploy-to-vps.sh` или merge в `main`
- **Ручной полный цикл:** Actions → **Run workflow** → `deploy: true`
  (с любой ветки, если нужен аварийный deploy)

Подробности инфра: [infra-reg-ru.md](infra-reg-ru.md).

Чтобы экономить минуты: копить коммиты, не пушить docs-only как code;
при нулевом бюджете Actions — ручной деплой:

```bash
./scripts/deploy-to-vps.sh
```

Подробности: [manual-deploy.md](manual-deploy.md).
