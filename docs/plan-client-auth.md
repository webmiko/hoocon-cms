# План: регистрация клиентов (email + пароль / OTP / Яндекс ID)

Дата: 2026-07-26  
Статус: **согласовано в плане**; код — **после** Iter 5 (SMTP / почта на сайте)  
Цель: публичная регистрация и вход; режимы A/B без сторонних CAPTCHA;
режим **C — Яндекс ID** (OAuth 2.0) как основа после A/B.

Связь: staff Admin остаётся на `django.contrib.auth` + Groups
(`accounts` staff). Клиентский auth — отдельный слой (расширение `accounts`
или app `clients`), **не** путать со staff.

Не в scope v1 MVP: ЛК дилера с остатками, корзина, OAuth Google,
Magic Link со сторонним сервисом.
**Яндекс ID** — не в MVP, но **заложен** в этом плане (§7), после режимов A/B
и HTTPS.

**Референс кода (БЗ-кандидат):** в `lms-backend` уже есть эталон без
сторонних CAPTCHA — `config/form_protection.py` (honeypot + signed
challenge + min-fill) и `config/admin_otp.py` (6-значный Email OTP).
План OAuth: `lms-backend/_plan-yandex-id-oauth.md` (ещё не в коде; PKCE,
обмен code на backend). В канон БЗ пока **не** перенесено — см.
[kb-update-proposals.md](kb-update-proposals.md) §5.
При имплементации Hoocon — портировать оттуда, не писать с нуля.

---

## 0. Гейт старта

| # | Условие | Зачем |
|---|---------|--------|
| 1 | SMTP prod/staging (Яндекс 360) работает | Доставка OTP / писем |
| 2 | Celery + Redis | Отправка писем; OAuth `state` / ticket в Redis |
| 3 | HTTPS | Secure cookies; Redirect URI Яндекс ID |

**Доп. гейт режима C (Яндекс ID):** зарегистрированное OAuth-приложение
в [oauth.yandex.ru](https://oauth.yandex.ru/client/new/id/), Redirect URI
prod + localhost, политика ПД обновлена.

---

## 1. Продуктовое решение

| Режим | Когда | Как работает |
|-------|-------|----------------|
| **A. Свой пароль** | Auth MVP | Email + пароль (Django hasher). |
| **B. Одноразовый код** | Auth MVP | Email без постоянного пароля; на каждый вход — **новый 6-значный код** на почту. |
| **C. Яндекс ID** | После A/B | Кнопка «Войти через Яндекс» на `/login` и `/register`; OAuth 2.0 + PKCE; auto-register при первом входе. |

- Режим B — не сторонний OTP-сервис: генерация и hash кода у нас, SMTP наш.
- Режим C — **IdP Яндекс** (это не CAPTCHA-виджет): `client_secret` только
  на backend; scopes минимум `login:email` + имя.
- Смена / привязка режимов (A↔B, привязка Яндекса к существующему email) —
  в фазе C (§7.3).

---

## 2. Модель (черновик)

- `ClientAccount` (или `User` с `is_staff=False` + профиль): email unique,
  `auth_mode`: `password` | `otp_email` | `yandex` (или флаг + social).
- Режим A: password hash; режим B: `EmailLoginCode` (code_hash, TTL, attempts).
- **Основа под C сразу при auth MVP:** модель `SocialAccount` /
  `UserSocialAccount` (`provider`, `provider_user_id`, FK user;
  `UniqueConstraint(provider, provider_user_id)`), даже если Yandex ещё
  выключен флагом — чтобы не мигрировать схему дважды.
- Сессия: Django session cookie (не JWT в `localStorage` —
  [security-baseline.md](security-baseline.md)). Отличие от LMS-плана
  (там JWT + ticket): у Hoocon после callback — login session, не
  `localStorage` access token.

---

## 3. API / UX (черновик) — режимы A/B

- `POST /api/auth/register/` — email, mode, password (только A), honeypot
  + throttle / challenge как в LMS form_protection.
- `POST /api/auth/login/` — A: email+password; B: email → код → verify-otp.
- `POST /api/auth/logout/`, `GET /api/auth/me/`.
- Письма OTP / опц. verify-email.

---

## 4. Безопасность (A/B)

- Код OTP: 6 цифр, RNG; в БД hash; TTL; max attempts; инвалидация старых.
- Throttle: per IP + per email.
- Антиспам форм — свой стек ([security-baseline.md](security-baseline.md)):
  **без** reCAPTCHA / hCaptcha / Turnstile. Яндекс ID — отдельный IdP, не CAPTCHA.
- Не логировать код/пароль; email — маска. IDOR на `/me/`.

---

## 5. Итерации A/B (после гейта SMTP)

- [ ] Модели + миграции + тесты register/login A и B
- [ ] Таблица `SocialAccount` (пустая / без провайдеров) — **задел под C**
- [ ] Celery-задачи писем OTP
- [ ] Публичные `/register`, `/login` (SPA); место под кнопку Яндекс (disabled
  или hidden, пока `YANDEX_OAUTH_ENABLED=false`)
- [ ] Связка с CRM `Client` по email (опц.)
- [ ] (не блокер A/B) дальше по очереди: ЛК —
  [plan-client-cabinet.md](plan-client-cabinet.md)

---

## 6. Критерии приёмки A/B

1. Режим A: регистрация и вход email+пароль; брутфорс ограничен.
2. Режим B: каждый вход — новый 6-значный код; просрочка / reuse / лимит → отказ.
3. Нет сторонней CAPTCHA в зависимостях.
4. Staff Admin не ломается; клиент не получает `is_staff`.
5. Модель `SocialAccount` и флаг `YANDEX_OAUTH_ENABLED` (default false) в
   settings / `.env.example` — готовы к фазе C.

---

## 7. Режим C — Яндекс ID (основа)

Канон деталей (адаптировать под Hoocon session, не JWT SPA LMS):
соседний репо `lms-backend/_plan-yandex-id-oauth.md` +
[док Яндекс ID](https://yandex.ru/dev/id/doc/ru/register-auth).

### 7.1. Решения (зафиксировать до кода C)

| # | Решение |
|---|---------|
| P1 | Authorization Code + **PKCE**; обмен `code` **только на backend** |
| P2 | Одна кнопка «Войти через Яндекс» на login и register; auto-register |
| P3 | Email уже есть с паролем → запрос пароля для **привязки** Яндекса |
| P4 | Email от Яндекса = подтверждённый |
| P5 | Consent ПД **до** редиректа на oauth.yandex.ru |
| P6 | Scopes: `login:email`, имя; аватар — later |
| P7 | Redirect URI: `https://hoocon.ru/api/auth/yandex/callback/` (+ localhost) |
| P8 | После callback — Django **session** login (не JWT в query / localStorage) |

### 7.2. Backend / frontend (чеклист)

- [ ] Settings: `YANDEX_OAUTH_CLIENT_ID`, `CLIENT_SECRET`, `ENABLED`;
  check: ENABLED без secret → `ImproperlyConfigured`
- [ ] `GET /api/auth/yandex/start/` → authorization_url; `state` + PKCE в Redis
- [ ] `GET /api/auth/yandex/callback/` → token + profile; find/create user +
  `SocialAccount`; `set_unusable_password()` если только Yandex; session login
- [ ] Throttle start/callback; whitelist хостов `oauth.yandex.ru`,
  `login.yandex.ru`; timeout; логи без code/token
- [ ] Open redirect guard на `next` / `from` (только path allowlist)
- [ ] SPA: кнопка, обработка ошибок привязки email
- [ ] Политика ПД / cookie: обработка данных через Яндекс ID
- [ ] Тесты: happy path, bad state, конфликт email → link flow

### 7.3. Не смешивать

- Яндекс ID ≠ антиспам форм (формы по-прежнему без сторонней CAPTCHA).
- Staff `/admin/` — **без** Яндекс ID (отдельный контур; опц. Email OTP staff
  как в LMS — отдельное решение).
- Google / VK ID / MAX login — **не** в этом плане (только мессенджеры в
  supportchat).

### 7.4. Критерии приёмки C

1. Вход и регистрация через Яндекс при `ENABLED=true`.
2. `client_secret` не во фронте; PKCE + state в Redis.
3. Сессия клиента после callback; нет токенов Яндекса в БД после profile.
4. Привязка к существующему email только после подтверждения пароля (или OTP).
