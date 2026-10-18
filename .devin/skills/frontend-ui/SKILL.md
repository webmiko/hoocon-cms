---
name: frontend-ui
description: Публичный UI hoocon-cms — вёрстка, CSS, шаблоны, frontend/**: Lighthouse/CWV/a11y чеклист, запрет горизонтального скролла на mobile, белый текст на красной заливке бренда. Вызывать при работе с frontend, CSS, HTML-шаблонами.
---

# Публичный UI

Прочитай и применяй канон:

- `.cursor/rules/frontend-public-ui.mdc` — чеклист перед коммитом
  с UI-diff: landmarks, один h1, alt, tokens→layers, rem/`clamp`
  (без 62.5%), CWV не ухудшать, CSP не ослаблять. Канон —
  `_docs/design-system.md` + веб-контур базы знаний.
- `.cursor/rules/mobile-no-horizontal-scroll.mdc` — без `100vw` у
  fixed/sticky, `min-width: 0` у flex/grid-детей, поля ввода ≥16px
  на touch, проверка узкого телефона с открытым оверлеем.
- `.cursor/rules/brand-fill-white-text.mdc` — на заливке logo-red /
  brand-control подпись только белая в обеих темах: токены
  `--color-on-brand-control` / `--color-on-brand-fill`,
  `data-brand-fill` на submit/ссылках.
