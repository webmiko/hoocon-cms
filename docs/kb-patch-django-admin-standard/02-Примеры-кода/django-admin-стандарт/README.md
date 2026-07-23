# Стандарт Django Admin (функционал + стиль)

Дата: 2026-07-23.  
Назначение: единый вариант staff-админки для проектов стека БЗ
(LMS / paywall, B2B-каталог CMS вроде Hoocon, рассылки и аналоги).

Официальные опоры:

- Django Admin:
  [docs.djangoproject.com](https://docs.djangoproject.com/en/stable/ref/contrib/admin/)
- django-unfold:
  [unfoldadmin.com/docs](https://unfoldadmin.com/docs/installation/quickstart/)

Референсы кода (вне канона БЗ, не копировать wholesale):

- `lms-backend` / OB2 — ModelAdmin-паттерны, session staff;
- `hoocon-cms` — B2B-каталог, RFQ, бренд-токены → `COLORS`.

---

## 1. Решение одной фразой

**Staff UI = Django Admin + django-unfold**, с палитрой `UNFOLD["COLORS"]`
из бренд-токенов проекта. Wagtail / React-admin — только по явному
решению (отдельный поток редакторов или отдельная роль).

| Вопрос | Ответ |
|--------|--------|
| Движок CRUD | Django Admin (`is_staff`, session + CSRF) |
| Оболочка UI | **django-unfold** (до `django.contrib.admin` в apps) |
| Цвета | `UNFOLD["COLORS"]["primary"]` из brand hex проекта |
| Тема | по умолчанию **light** (B2B/LMS); dark — опция, не default |
| Wagtail | не v1 для каталога/CRUD (см. проектные docs) |
| Корзина / оплата | не в scope v1 B2B; RFQ / заявки |

---

## 2. Когда применять

Использовать этот стандарт, если:

- есть staff/менеджер, который правит модели без деплоя;
- домен — таблицы, фильтры, файлы, заявки, настройки сайта;
- нужен узнаваемый UI под бренд заказчика без отдельного SPA-admin.

Не использовать как единственный UI, если:

- нетехнари правят блочную вёрстку лендингов ежедневно → Wagtail
  (этап 2, отдельно от каталога);
- нужна отдельная роль «менеджер каталога» с JWT SPA → React-admin
  поверх DRF (явно в плане проекта).

---

## 3. Состав модуля

| Файл | Содержание |
|------|------------|
| [функционал.md](функционал.md) | ModelAdmin, apps, security, sidebar |
| [стиль-и-цвета.md](стиль-и-цвета.md) | Unfold, brand → OKLCH, light UI |
| [примеры/](примеры/) | фрагменты settings / admin / colors |

---

## 4. Чеклист внедрения в новый проект

1. `poetry add django-unfold` (или pip/uv).
2. `unfold` (+ опц. `unfold.contrib.filters` / `forms`) **перед**
   `django.contrib.admin` в `INSTALLED_APPS`.
3. Все `@admin.register` → `from unfold.admin import ModelAdmin`.
4. Заполнить `UNFOLD`: `SITE_HEADER`, `SITE_TITLE`, `COLORS`, `SIDEBAR`,
   `BORDER_RADIUS`, при необходимости `SITE_LOGO`.
5. Вывести primary-палитру из brand hex (рецепт в стиль-и-цвета.md).
6. Auth: только staff; throttle login; без JWT в localStorage для public.
7. Smoke: login → changelist → change → save; anon → redirect login.

Подробности: функционал.md §безопасность, стиль-и-цвета.md §рецепт.
