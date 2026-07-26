# Предложения пополнения базы знаний (из исследования Hoocon)

Дата: 2026-07-19.  
Обновлено: 2026-07-26 — аудит БЗ vs Iter 6 (антиспам / OTP / поддержка).  
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
| Антиспам публичных форм (без CAPTCHA) | §5 ниже + `lms-backend` form_protection |
| Email OTP (свой код, без MFA SaaS) | §5 ниже + `lms-backend` admin_otp |
| Admin inbox поддержки / мессенджеры | пока только `hoocon-cms` plan; в БЗ — нет |

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

## 5. Аудит БЗ: антиспам / OTP / поддержка (2026-07-26)

Сверка канона БЗ с планом Hoocon Iter 6 и живым кодом **lms-backend**.

### 5.1. Что есть в БЗ сейчас

| Тема | В БЗ | Где |
|------|------|-----|
| DRF throttle / axes | Частично | `безопасность/Django-DRF-безопасность.md`, `Фулстек-разработка-2026.md` |
| Rate limit на login | Да (общее) | `Безопасность-кода.md`, SDLC (упоминает captcha как опцию STRIDE) |
| Honeypot + signed challenge | **Нет** | — |
| «Без сторонней CAPTCHA» | **Нет** как политика | SDLC даже пишет «captcha» в митигации DoS |
| Email OTP 6 цифр (свой SMTP) | **Нет** | — |
| Admin inbox / чат + TG/VK/MAX | **Нет** | только проектный `hoocon-cms/docs/plan-support-chat-social.md` |
| Регистрация dual-mode пароль/OTP | **Нет** | проектный `plan-client-auth.md` |
| Яндекс ID (OAuth login/register) | **Нет** | план в `lms-backend/_plan-yandex-id-oauth.md` (код ещё нет); Hoocon — `plan-client-auth.md` §7 |

В `02-Примеры-кода/lms-backend/` (README, РЕФЕРЕНС, ОПЫТ-PROD, ЖУРНАЛ) **не
задокументированы** `form_protection` и `admin_otp`, хотя код в репо есть.

### 5.2. Эталон в lms-backend (переносить в БЗ)

Антиспам **без сторонних сервисов** (уже на prod/конфиге LMS):

| Компонент | Путь в `lms-backend/` |
|-----------|------------------------|
| Ядро | `config/form_protection.py` — honeypot, `TimestampSigner` challenge, `too_fast` (min seconds), Origin/Referer |
| API challenge | `config/form_protection_views.py` — `GET` scope → token + имя honeypot |
| Env | `FORM_PROTECTION_*`, `FORM_HONEYPOT_FIELD=company_url` — `wiki/configuration.md` |
| Тесты | `tests/test_form_protection.py` |
| UI | `frontend/.../RegisterPage.tsx`, `ForgotPasswordPage.tsx` |
| + | disposable email blocklist при register |

Email OTP **без MFA SaaS** (admin; паттерн пригоден для клиентского OTP):

| Компонент | Путь |
|-----------|------|
| Ядро | `config/admin_otp.py` — 6 цифр `secrets`, hash+pepper, cache, TTL, attempts, resend cooldown |
| Views | `config/admin_otp_views.py` |
| Backoff | `config/admin_login_backoff.py` (scope `admin` / `admin_otp`) |
| Тесты | `tests/test_admin_email_otp.py`, часть `tests/test_brute_force.py` |
| Env | `ADMIN_EMAIL_OTP_*` |

### 5.3. Gap Hoocon vs LMS

| | Hoocon сейчас | LMS эталон |
|--|---------------|------------|
| Lead RFQ | honeypot `website` + throttle `lead_create` | honeypot + **signed challenge** + min-fill time + Origin |
| Register/OTP | только план | register уже с form_protection; OTP — admin |
| Поддержка inbox | план `plan-support-chat-social` | в LMS нет аналога → новый паттерн из Hoocon после ship |

**Рекомендация при имплементации Hoocon:** не изобретать заново —
портировать `form_protection` (+ challenge) на leads / будущий auth;
для режима B (OTP-вход) — адаптировать `admin_otp` (hash, TTL, attempts)
под публичный client-login, не staff.

### 5.4. Кандидаты документов в канон (после согласования)

1. **`02-Примеры-кода/lms-backend/ПАТТЕРНЫ-FORM-PROTECTION-OTP-LMS.md`**
   — honeypot + challenge + Email OTP; ссылки на файлы; «без reCAPTCHA».
2. Строка в `безопасность/README.md` дерево решений:
   «Антиспам форм / Email OTP → паттерн LMS».
3. Уточнить в `Жизненный-цикл-безопасности-SDLC.md`: captcha ≠ обязательный
   сторонний виджет; предпочтение — свой стек (как LMS).
4. После ship Hoocon: короткий абзац в `hoocon-cms/` про Admin «Поддержка»
   (inbox ≠ broadcast SocialPost).
5. Обновить `lms-backend/README.md` таблицу «Ключевые файлы» —
   `form_protection.py`, `admin_otp.py`.
6. После реализации Яндекс ID (LMS или Hoocon): паттерн OAuth+PKCE в
   `02-Примеры-кода/` + строка в `безопасность/README.md` (IdP ≠ CAPTCHA).

---

## 6. Статус

- [ ] Согласовать с пользователем перенос (§1 B2B + §5.4 антиспам/OTP)
- [ ] Написать конспект ≤119 символов/строка
- [ ] Обновить AGENTS.md / README / ИЗМЕНЕНИЯ.md канона
- [ ] Добавить референс после появления кода в `hoocon-cms`
- [x] Аудит gap БЗ vs LMS form_protection / admin_otp (2026-07-26)
