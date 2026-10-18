---
name: catalog-cards
description: Карточки товаров hoocon-cms — новые Product/SKU наполнять из мануалов сразу (ТТХ, PDF, фото); шаблоны серий DA/SA/8100/H81/H8205 и синхрон канона с кодом. Вызывать при работе с backend/catalog, ETL серий, collapse/siblings/picker карточек.
---

# Карточки ← мануалы; шаблоны серий

Прочитай и применяй канон:

- `.cursor/rules/cards-from-manuals.mdc` — при заведении Product/SKU с
  готовой инструкцией сразу бери ТТХ/copy из RU-мануала, PDF через
  `attach_manual_pdfs`, фото/схемы из ассетов мануала. Нельзя: seed
  «пустышка», ТТХ из старого EN при наличии RU.
- `.cursor/rules/series-card-templates.mdc` — канон
  `_docs/series-card-templates.md`; при смене поведения карточки серии
  обнови соответствующий § канона и синхронизируй код по матрице
  «куда править» (family_cards.py + h81CatalogCollapse.ts, siblings.py +
  FE resolve/picker, ball_valve_kit.py для 8100); не ломай slug-схемы
  `8100-bv*`, `h81xx`, `h8205-lav*`; регресс-тест на collapse/siblings.
