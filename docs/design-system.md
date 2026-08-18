# Дизайн-система Hoocon SPA

Дата: 2026-08-03  
Канон: [readiness-backend-ux.md](readiness-backend-ux.md) §4;
прототипы `../hoocon/docs/прототипы/`; БЗ `ПРОМПТ_РАЗРАБОТКИ/03_ДИЗАЙН_И_UX.md`;
типографика (общий канон) —
`_Универсальная-база-знаний/…/Lighthouse-HTML-CSS-архитектура.md` §1.1.

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
| Glass | `--glass-blur: 18px`, `--glass-bg` ~90% white; header/menus |
| UI font | IBM Plex Sans |
| Display | Montserrat (логотип, H1–H3) |
| Motion | `280ms cubic-bezier(0.22, 1, 0.36, 1)` |

Body-ссылки — `#b01010` (контраст AA на белом). CTA — заливка `#dc1313`.

> **Prod vs Vite:** не убирать `backdrop-filter` при minify. Vite/LightningCSS
> иначе оставляет только `-webkit-backdrop-filter` → в Firefox blur почти
> пропадает. Канон фикса: `frontend/vite.preserve-backdrop-filter.ts`.

## Типографика (размеры и адаптив)

Корень: `html { font-size: 100% }` (браузерный default ≈16px). **Не** ставить
`62.5%` / `10px` на `html` — ломает user font-size и a11y.

Шкала только через токены `rem` + `clamp()` в `tokens.css`. Body floor —
`1rem`; chrome `--font-size-sm` ≈ 0.875rem. Заголовки — отдельная иерархия
(`--font-size-h1`…`h5`), не те же токены, что UI large.

| Токен | Назначение |
|-------|------------|
| `--font-size-sm` | chrome: chips, meta, catalog card titles (~0.875) |
| `--font-size-base` | body / UI (≥ 1rem) |
| `--font-size-lg` | лиды, акценты в карточках |
| `--font-size-xl` / `--font-size-2xl` | UI large (цена, empty), не page H1 |
| `--font-size-h1`…`--font-size-h5` | иерархия заголовков (H1 700/1.25, H2–H3 600) |
| `--font-size-hero` | wordmark / landing hero |

**H1 страницы ≠ заголовок карточки.** Семантический `h3.cardTitle` в каталоге
остаётся `--font-size-sm`; глобальный H3 его не раздувает. Длинные имена SKU
на PDP — `--font-size-h2`, не page H1.

### Правила агента

1. Новый `font-size` в компонентах — `var(--font-size-*)` или `rem`/`clamp`,
   не «голые» `px` (кроме исключения ниже).
2. **Исключение iOS:** `font-size: 16px` только на `<input>` / `<textarea>` /
   search fields — иначе Safari зумит страницу при фокусе. Глобальный
   guard в `global.css` (`!important` на coarse pointer); CSS modules
   **не** должны ставить на эти контролы кегль &lt; 16px / 1rem.
3. Семейства: `--font-sans` (UI), `--font-display` (бренд / заголовки);
   preload + `font-display: swap`.
4. Длинные RU-заголовки в узких карточках: `text-wrap: pretty` (или обычный
   wrap). **Не** `text-wrap: balance` — на узкой ширине дробит на 4–6 коротких
   строк (направления на главной, chips). Body — `pretty`.
5. Длинные SKU / артикулы: `softBreak()` (ZWSP после `|` / `-`), без
   `word-break: break-word` «на всякий случай».
6. На узких каруселях / колонках: чуть мельче кегль + меньше горизонтальный
   padding текста, чтобы длинное имя уложилось в 2–3 строки, а не в «столбик».
7. **Fixed / sticky оверлеи:** не `width: …100vw…`. Корень — `left`+`right`
   (inset), панель — `min(…px, 100%)` + `min-width: 0`. Иначе на mobile
   появляется горизонтальный скролл (чат, баннеры). Правило агента:
   `.cursor/rules/mobile-no-horizontal-scroll.mdc`.

## Компоненты

- **Layout:** frosted-glass sticky header; masthead desktop; burger ≤960px;
  тёмный футер; floating glass CTA на mobile; cookie над CTA.
- **Home:** brand-first hero с мягкими градиентами; glass trust tiles;
  направления и шаги с воздухом; лёгкий `rise` на появление.
- **Catalog / PDP:** glass-карточки; ТТХ — `dl`-карточки; hover lift 2–3px.
- **Адаптив:** `overflow-x: clip`; больше вертикальных отступов (`--space-2xl/3xl`);
  fixed-оверлеи без `100vw` (inset `left`/`right` + `width: min(…, 100%)`).
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
