---
name: cms-content
description: CMS-контент hoocon-cms — статьи, новости, лендинги, ETL-копирайт: дашборды/графики вместо стен текста, буква ё в русском тексте. Вызывать при работе с backend/content, fixtures, ETL-текстами, пользовательским русским copy.
---

# CMS-контент и русский текст

Прочитай и применяй канон:

- `.cursor/rules/cms-content-dashboards.mdc` — блоки цифр передавать
  дашбордами `.dash`/`.dash-panel` (donut, meter, hbar, vbar, kpi-tiles,
  funnel), только HTML+CSS-классы (sanitizeHtml режет svg/style/data-*),
  стили в `frontend/src/styles/cms-body-charts.css`, референс —
  `backend/content/fixtures/page_zavod.html`.
- `.cursor/rules/russian-yo.mdc` — в любом пользовательском и контентном
  русском тексте не заменять ё на е; «все» ≠ «всё»; чертежи (мн.ч.) без ё;
  код, идентификаторы, URL не трогать. Техкопирайт —
  `_docs/tech-copy-belimo-ru.md`.
