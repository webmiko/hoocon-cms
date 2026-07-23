# Стандарт staff-админки (Hoocon CMS)

Дата: 2026-07-23.

**Канон для переноса в главную БЗ:**
[kb-patch-django-admin-standard/](kb-patch-django-admin-standard/)
(раздел `02-Примеры-кода/django-admin-стандарт/`).

Пока симлинк `_Универсальная-база-знаний` на машине агента битый,
этот документ — **операционный эталон** проекта. После копирования
патча в канон БЗ приоритет у файлов базы.

---

## Решение

| Слой | Выбор |
|------|--------|
| CRUD | Django Admin, session + CSRF, `is_staff` |
| UI | **django-unfold** (до `django.contrib.admin` в apps) |
| Цвета | `UNFOLD["COLORS"]["primary"]` из brand `#dc1313` |
| Тема | light, `BORDER_RADIUS=8px` (как публичные токены) |
| Не в v1 | Wagtail; React-admin; корзина/оплата |

Согласовано с [admin-vs-wagtail.md](admin-vs-wagtail.md),
[stack-decision.md](stack-decision.md),
[readiness-backend-ux.md](readiness-backend-ux.md) §4.2,
[security-baseline.md](security-baseline.md).

Тот же вариант — для LMS-подобных проектов: тот же Unfold + ModelAdmin,
другой brand hex и пункты SIDEBAR.

---

## Внедрение в Hoocon (итерация 1+)

1. `poetry add django-unfold` в `backend/`.
2. Подключить apps + `UNFOLD` (см. патч `примеры/`).
3. `brand_colors.py` с primary от `#dc1313`.
4. Регистрировать модели через `unfold.admin.ModelAdmin`.
5. SIDEBAR: Каталог / Контент / Заявки / Redirect / SiteSettings.
6. Тесты: staff write, anon 403, цены не в public API без флага.

---

## Применение патча в БЗ

Инструкция: [kb-patch-django-admin-standard/APPLY.md](kb-patch-django-admin-standard/APPLY.md).
