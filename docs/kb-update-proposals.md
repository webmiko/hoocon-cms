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

## 5. Статус (B2B-каталог)

- [ ] Согласовать с пользователем перенос
- [ ] Написать конспект ≤119 символов/строка
- [ ] Обновить AGENTS.md / README / ИЗМЕНЕНИЯ.md канона
- [ ] Добавить референс после появления кода в `hoocon-cms`

---

## 6. Стандарт Django Admin (2026-07-23) — готовый патч

**Статус:** текст готов; в канон БЗ ещё не скопирован (в cloud-агенте
симлинк `_Универсальная-база-знаний` → Mac-путь **битый**).

**Патч в репо:** [kb-patch-django-admin-standard/](kb-patch-django-admin-standard/)  
**Операционный эталон:** [admin-standard.md](admin-standard.md)  
**APPLY:** [kb-patch-django-admin-standard/APPLY.md](kb-patch-django-admin-standard/APPLY.md)

Содержание для канона:

- путь БЗ: `02-Примеры-кода/django-admin-стандарт/`;
- функционал ModelAdmin / sidebar / security (LMS + B2B CMS);
- стиль django-unfold; `COLORS.primary` из brand hex проекта;
- light-тема по умолчанию; примеры settings/admin/brand_colors;
- snippets: AGENTS.md, веб-стек README, ИЗМЕНЕНИЯ.md.

- [x] Согласовать вариант (Unfold + бренд-цвета) для Hoocon и LMS
- [x] Написать конспект ≤119 символов/строка (в патче)
- [ ] Скопировать в канон `/Users/niko/GitHub/Универсальная-база-знаний`
- [ ] Обновить AGENTS.md / README / ИЗМЕНЕНИЯ.md **канона** БЗ
