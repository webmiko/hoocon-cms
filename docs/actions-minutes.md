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

Один полный CI (test → lint → build → deploy) обычно **~5–15 мин**
в зависимости от кэша Docker/npm. При лимите 500/нед это примерно
**30–100 деплоев в неделю** — на практике упираетесь раньше в время
сборки, чем в число пушей.

## Связь с деплоем

Канон: push в `develop` / `main` → Actions → VPS
([infra-reg-ru.md](infra-reg-ru.md)).
Чтобы экономить минуты: копить коммиты и пушить пачкой в конце дня;
при нулевом бюджете Actions — ручной деплой:

```bash
./scripts/deploy-to-vps.sh
```

Подробности: [manual-deploy.md](manual-deploy.md).
