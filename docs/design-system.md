# Дизайн-система Hoocon SPA

Дата: 2026-07-19  
Канон: [readiness-backend-ux.md](readiness-backend-ux.md) §4;
прототипы `../hoocon/docs/прототипы/`; БЗ `ПРОМПТ_РАЗРАБОТКИ/03_ДИЗАЙН_И_UX.md`.

## Назначение

Единый визуальный язык industrial B2B для инженера / снабженца / дилера.
Источник токенов в коде: `frontend/src/styles/tokens.css`.

## Токены

| Роль | Значение |
|------|----------|
| Brand | `#dc1313` / hover `#b01010` / soft `rgba(220,19,19,.09)` |
| Text | `#2a2a2a` / `#5a5a5a` / `#8a8a8a` |
| Page | мягкий `--gradient-page` (не flat) |
| Glass | `rgba(255,255,255,.90–.96)` + `blur(18px)` |
| Radius | concentric: xs 6 / sm 10 / md 14 / lg 18 / xl 24
  (крупнее блок → крупнее радиус) |
| Shadow | `0 12px 40px rgba(20,20,30,.06)` — один слой |
| UI font | IBM Plex Sans |
| Display | Montserrat (логотип, H1–H3) |
| Motion | `280ms cubic-bezier(0.22, 1, 0.36, 1)` |

Body-ссылки — `#b01010` (контраст AA на белом). CTA — заливка `#dc1313`.

## Компоненты

- **Layout:** frosted-glass sticky header; masthead desktop; burger ≤960px;
  тёмный футер; floating glass CTA на mobile; cookie над CTA.
- **Home:** brand-first hero с мягкими градиентами; glass trust tiles;
  направления и шаги с воздухом; лёгкий `rise` на появление.
- **Catalog / PDP:** glass-карточки; ТТХ — `dl`-карточки; hover lift 2–3px.
- **Адаптив:** `overflow-x: clip`; больше вертикальных отступов (`--space-2xl/3xl`).
- **Текст:** `text-wrap: balance` на заголовках, `pretty` на body; `softBreak()` для
  длинных SKU (перенос после `|` / `-`, без mid-word shatter).
- **A11y:** skip-link, `focus-visible`, `prefers-reduced-motion`.

## Антипаттерны (не использовать)

- Carbon / IBM blue, purple gradients, cream + serif terracotta
- Neon glow, multi-layer shadows, rounded-full pills, emoji
- Иконки Cart / Wishlist; карточки в hero
- Тяжёлый glassmorphism (яркие блики, насыщенный blur >24px)

## Motion (CWV-safe)

- Появление секций: `rise` ~0.7s, stagger ≤180ms
- Hover: `translateY(-2px)` + мягкая тень
- Без параллакса, loop-анимаций и motion на LCP-изображениях
