# Предложения пополнения базы знаний (из исследования Hoocon)

Дата: 2026-07-19.  
Правило: править только канон `/Users/niko/GitHub/Универсальная-база-знаний`
по `ИНСТРУКЦИЯ-ПО-ОБНОВЛЕНИЮ-БАЗЫ-ЗНАНИЙ.md`. Ниже — **кандидаты**, не авто-патч.

---

## 1. Новый раздел (черновик темы)

**Путь (предложение):**
`02-Примеры-кода/b2b-catalog-cms/` или
`01-Учебные-материалы/15-Основы-веба/B2B-каталог-и-CMS.md`

**Содержание:**

- модель Category / Product / SKU / Attribute;
- фильтры через query params + индексы;
- RFQ вместо корзины;
- поиск: Postgres FTS → Meilisearch;
- SEO Product JSON-LD;
- разделение «контент-страницы» vs «товарные сущности».

**Официальные опоры:**

- Django: [Full text search](https://docs.djangoproject.com/en/stable/ref/contrib/postgres/search/)
- DRF: [Filtering](https://www.django-rest-framework.org/api-guide/filtering/)
- Wagtail: [docs.wagtail.org](https://docs.wagtail.org/)
- Meilisearch:
  [Filtering & faceting](https://www.meilisearch.com/docs/learn/filtering_and_sorting/search_with_facet_filters)

---

## 2. Дополнить маршрутизацию AGENTS.md

Строка в таблице задач:

| Задача | Куда |
|--------|------|
| B2B-каталог / CMS без корзины | новый конспект + референс `hoocon-cms` |

---

## 3. Веб-стек README

В `04-Инструкции-разработки/ВЕБ-РАЗРАБОТКА-Кастомный-стек/README.md` добавить
ветку:

```
Публичный B2B-каталог?
├─ ДА → Product models + RFQ; SEO Product; фильтры в URL
└─ LMS/paywall → существующая ветка
```

---

## 4. Чего не класть в БЗ

- чужие тексты/фото с Belimo/Dastech;
- цены и коммерческие условия Hoocon;
- сырые CSV из `hoocon/data` без анонимизации.

---

## 5. Статус

- [ ] Согласовать с пользователем перенос
- [ ] Написать конспект ≤119 символов/строка
- [ ] Обновить AGENTS.md / README / ИЗМЕНЕНИЯ.md канона
- [ ] Добавить референс после появления кода в `hoocon-cms`
