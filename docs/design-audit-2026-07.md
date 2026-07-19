# Аудит дизайна Hoocon SPA (2026-07-19)

Канон: [design-system.md](design-system.md), [readiness-backend-ux.md](readiness-backend-ux.md) §4.

## 1. Что сильно (не трогать)

- **Единая токенизация**: `--color-brand`, `--glass-bg`, `--radius-*`, `--space-*` — собраны в `tokens.css`; нет magic values повсеместно.
- **Industrial B2B стиль**: красный бренд, мягкое glass, IBM Plex Sans + Montserrat; не уходит в lifestyle или неон.
- **Адаптивная основа**: `--bottom-chrome`, `overflow-x: clip`, контейнер с `--max-width`;
  mobile-меню с блокировкой скролла и Escape.
- **Доступность**: skip-link, `focus-visible`, `prefers-reduced-motion`, `aria-label` на навигации, `text-wrap`/`softBreak`.
- **Motion-safe**: `rise` и hover-lift 2 px без параллакса и loop-анимаций; CWV-safe.
- **SEO**: двухслойный head, canonical, JSON-LD, noindex на служебных маршрутах.

## 2. Расхождения и что улучшить

### 2.1 Визуальная иерархия и плотность

| Проблема | Где | Решение |
|----------|-----|---------|
| Слишком много «стекла» друг на друга | home, catalog | Ввести не-glass секции как отдушину; glass-тайлы хорошо, но каждый второй блок в стекле утомляет |
| Карточки каталога — компактные, но читаемость цены/артикула страдает | CatalogPage | Для `gridSingle` (категория) можно чуть больше gap и разделить строки highlight (момент/напряжение) визуально |
| Hero на home — очень высокий, brand 4 rem может быть громоздким на ноутбуке | HomePage | Уменьшить `clamp(2.5rem, 8vw, 4rem)` до `clamp(2rem, 6vw, 3.25rem)`; добавить `min-height` hero 55–60 vh |
| Trust tiles накладываются на hero с `margin-top: -var(--space-lg)`; на мобильном могут прилипать | HomePage | `margin-top: calc(-1 * var(--space-lg))` → добавить `@media (max-width: 768px)` с меньшим перекрытием или убрать overlap на mobile |
| H1 PDP `--font-size-xl` (24px) мелковат для страницы товара | SkuDetailPage | Поднять до `clamp(1.25rem, 2.5vw, 1.75rem)` |

### 2.2 Компоненты и паттерны

| Проблема | Где | Решение |
|----------|-----|---------|
| Выпадающее cookie + mobile CTA могут конфликтовать | Layout/CookieConsent | `bottom-chrome` учитывает CTA; проверить, что cookie не перекрывает навигацию; при раскрытом меню cookie можно убирать или поднять |
| Нет skeleton/placeholder для медленной загрузки | CatalogPage, HomePage | Вместо текста «Загрузка…» — стеклянные pulse-skeleton блоки (сохраняя glass-эстетику) |
| Нет sticky TOC / навигации внутри длинного PDP | SkuDetailPage | Табы уже есть, но при скролле вниз по описанию их не видно → сделать tabList sticky под header или якорную навигацию |
| Фото в карточках используют `object-fit: cover` + left top — может обрезать длинные приводы | CatalogPage | У `object-fit: cover` есть риск; для B2B лучше `contain` с фиксированным квадратом, если фото уже на белом. Сейчас `cover` + left top — проверить, не уезжают ли важные детали |
| В каталоге facet chips — 12px, плохая touch-target | CatalogPage | Увеличить до 14px padding и min-height 36 px для mobile |

### 2.3 Типографика и цвет

| Проблема | Где | Решение |
|----------|-----|---------|
| `--font-size-sm: 14px` в chips — близко к низу читаемости | CatalogPage | Минимум 14 px ок, но для длительного чтения specs лучше 15 px base; уже так |
| Ссылки в body `#b01010` — OK, но visited не стилизован | global.css | Добавить `:visited` менее насыщенный цвет (для accessibility и orientation) |
| Все CTA красные — нет вторичного приоритета | global | «Запросить КП» всегда primary; «Смотреть каталог» может быть secondary outline на светлых фонах |
| Тёмный футер и hero — хорошо, но переход от page wash к footer резкий | global | Добавить footer-gradient или `margin-top: 0` + фоновая связка |

### 2.4 CWV / performance / UX

| Проблема | Где | Решение |
|----------|-----|---------|
| `background-attachment: fixed` на body — jank на iOS / Safari | global.css | Заменить на `background: …` без `fixed` или на `::before` с `position: fixed` |
| Hero image не показывается на home — есть только текст | HomePage | Это сознательно, но для доверия стоит добавить фото производства/сертификат или схему в hero (не lifestyle, а industrial) |
| Нет focus-стилей на glass-элементах | карточки, чипы | Добавить `outline: 2px solid var(--color-brand)` с `outline-offset: 2px` на `:focus-visible` |
| Gallery на PDP aspect-ratio 4/3, но фото квадратные | SkuDetailPage | Привести к `1/1` или `3/4` в зависимости от источника фото |

### 2.5 Современные тренды (2025–2026), которые можно взять

1. **Bento-расположение** на главной: hero + 3–4 compact tiles (склад, сертификаты, аналоги, КП) вместо отдельной trust-полосы.
2. **Micro-interactions**: press-in на кнопках (`scale(0.98)` + shadow drop) вместо только lift; лифт оставить на карточках.
3. **Container queries** для карточек SKU: когда `gridSingle` — карточка сама знает, что у неё больше места.
4. **Better empty states**: «Ничего не найдено» с иконкой/иллюстрацией и CTA «Сбросить фильтры»; сейчас только текст.
5. **Consistent radius**: радиусы уже concentric, но кнопки/чипы `--radius-sm` vs карточки `--radius-lg` — ок, но проверить, что кнопки внутри карточек не «выбиваются».

## 3. Приоритеты (что делать первым)

| Приоритет | Задача | Оценка |
|-----------|--------|--------|
| P1 | Сделать cookie banner безопасным для mobile (не конфликт с CTA) | 1 файл |
| P1 | Skeleton для загрузки каталога/главной | 2 файла |
| P2 | Улучшить PDP H1 + sticky tabs | 2 файла |
| P2 | Ввести `:visited` и `focus-visible` | global + кнопки |
| P3 | Bento hero + press-in micro-interactions | 3–4 файла |
| P3 | `background-attachment: fixed` → fixed pseudo-element | global.css |

## 4. Чеклист перед коммитом дизайна

- [ ] Изменения не ломают glass-стиль (не добавлены neon/blue)
- [ ] `prefers-reduced-motion` сохранён
- [ ] Нет `!important` в новых стилях
- [ ] Цвета/тени взяты из tokens.css
- [ ] Mobile проверено в DevTools 375px и 768px
- [ ] a11y: focus-visible, contrast ≥ AA
