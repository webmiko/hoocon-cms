# Security baseline: Hoocon CMS (secure by default)

Дата: 2026-07-19 (обновлено 2026-07-26: антиспам без сторонней CAPTCHA)  
Опора: внутренняя база знаний (безопасность кода, OWASP Top 10:2025,
Django/DRF, Frontend SPA, инфра TLS/Docker) и стандарты разработки §0 / §4.

Принцип: **безопасность с итерации 1**, не «потом на prod».  
Нет корзины/оплаты в v1 — поверхность уже уже; остаются: публичные формы,
Admin, файлы, SPA, VPS.

---

## 1. Threat model (кратко)

| Актив | Угроза | Контроль |
|-------|--------|----------|
| Staff Admin / сессии | Брутфорс, CSRF, XSS в Admin | HTTPS, CSRF, rate limit login, сильные пароли |
| Публичный RFQ `POST /api/leads/` | Спам, injection, PII scrape | Serializer validate, honeypot, throttle, CSRF/API |
| Каталог / цены в БД | Утечка цен через API | `show_prices` + serializer; нет цены по умолчанию |
| PDF / media | Path traversal, malware upload, hotlink | allowlist MIME, size; nginx+Django Referer allowlist on `/media/` |
| SEO head / JSON-LD | XSS через контент | whitelist полей, `html.escape`, без сырого HTML |
| SMTP / `.env` | Утечка секретов | только env; не в логах; `.gitignore` |
| Зависимости | Supply chain | poetry.lock, npm lock, `pip-audit` в CI |
| VPS reg.ru | Misconfig, открытые порты | nginx TLS, DEBUG=False, firewall, fail2ban |

---

## 2. OWASP Top 10:2025 → решения проекта

| Категория | Как закрываем в Hoocon CMS |
|-----------|----------------------------|
| A01 Broken Access | Admin только staff; публичный API read-only; Lead create без эскалации прав |
| A02 Security Misconfiguration | Prod: DEBUG=False, ALLOWED_HOSTS, SECURE_*, CSP, CORS whitelist |
| A03 Supply Chain | lock-файлы; `pip-audit`; npm audit в CI; минимум deps |
| A04 Cryptographic Failures | SECRET_KEY из env; TLS на VPS; пароли Django hasher; SMTP TLS |
| A05 Injection | ORM/параметры; DRF serializers; нет `shell=True` / `eval` |
| A06 Insecure Design | RFQ без оплаты; цены скрыты; threat model выше |
| A07 Auth Failures | Session+CSRF для Admin; throttle login; нет JWT в localStorage для v1 public |
| A08 Software/Data Integrity | ETL validate; не доверять HTML Tilda as-is |
| A09 Logging/Monitoring | Логи без PII/секретов; health; позже алерты |
| A10 SSRF | Нет произвольных URL от пользователя; исходящие только SMTP/known |

---

## 3. Правила по слоям (обязательные)

### 3.1 Секреты и settings

- Секреты только в `.env` (не в git). `.env.example` — плейсхолдеры.
- Prod: `DJANGO_SECRET_KEY` **обязателен**; insecure default запрещён при
  `DEBUG=False` (`ImproperlyConfigured`).
- `DJANGO_DEBUG=False` на VPS; `ALLOWED_HOSTS` явный список.
- **Postgres обязателен** для `migrate` (FTS/GIN/triggers). `USE_SQLITE=True` —
  только аварийный/ограниченный режим; полный локальный стек — Postgres.
- Prod cookies: `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS,
  `SECURE_SSL_REDIRECT` (за reverse proxy — `SECURE_PROXY_SSL_HEADER`).
- **COOP** (`SECURE_CROSS_ORIGIN_OPENER_POLICY`): default off на HTTP IP
  (браузер игнорирует заголовок → шум в консоли/Lighthouse). После домена+TLS:
  `DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin`.
- Prod: Redis `CACHES` для DRF throttle (не LocMem per-worker).
- OpenAPI `/api/schema/`, `/api/docs/` — только staff при `DEBUG=False`.

### 3.2 Django / DRF

- CSRF включён для session; CORS — whitelist origin (Vite/prod domain), не `*`.
- Публичные POST (leads и будущие auth/чат-формы): `AnonRateThrottle` +
  honeypot-поле.
  **Политика CSRF (v1):** SPA берёт токен через `GET /api/csrf/` и шлёт
  `X-CSRFToken` на `POST /api/leads/` (см. `frontend/src/api/client.ts`).
  Throttle shared через Redis `CACHES` в prod (`DJANGO_CACHE_URL` / DB 2).
  **Антиспам без сторонних сервисов:** не подключаем reCAPTCHA, hCaptcha,
  Turnstile и аналоги (ни виджет, ни серверный SDK). Защита — свой стек:
  honeypot, throttle, CSRF, валидация длины/полей; при эскалации спама —
  усилить timing/min-submit и лимиты, не внешний CAPTCHA.
  **Эталон:** `lms-backend` `config/form_protection.py` (+ challenge,
  Origin) и `config/admin_otp.py` (6-значный код на email). В БЗ-каноне
  паттерн ещё не оформлен — кандидат в
  [kb-update-proposals.md](kb-update-proposals.md) §5.
  **Яндекс ID** (OAuth) — отдельный IdP для входа клиентов, не CAPTCHA;
  план: [plan-client-auth.md](plan-client-auth.md) §7; `client_secret` только
  backend; после callback — session, не JWT в localStorage.
- **Соцсети / боты:** токены и chat ID — только Admin (`SiteSettings`) или
  `.env` (fallback). В `GET /api/settings/public/` — только analytics IDs.
- Сериализаторы: explicit fields; mass assignment закрыт.
- Ошибки API: без stack trace клиенту; логировать `type(e).__name__`.
- Admin: только staff; опц. IP allowlist nginx на `/admin/` (prod).
  **Email OTP:** при `ADMIN_EMAIL_OTP_ENABLED=true` вход без пароля —
  логин/email → 6-значный код на почту (`config/admin_otp.py`). SMTP
  обязателен. TTL кода короткий (дефолт 60 с); allowlist
  `ADMIN_EMAIL_OTP_ALLOWED_EMAILS`; progressive delay на неверный код;
  rate limit запросов кода по IP (+ django-axes). При `false` —
  классический пароль (локалка/CI/авария).

### 3.3 Файлы и ETL

- Upload: max size, allowlist `pdf/jpeg/png/webp`; имя генерировать сервером.
- Path: resolve + `is_relative_to(MEDIA_ROOT)`.
- Hotlink: Referer allowlist на `/media/` (nginx `valid_referers` +
  `MediaHotlinkMiddleware`); пустой Referer разрешён (прямая вкладка / PDF в
  почте). Чужой сайт с `<img src="https://hoocon…/media/…">` → 403.
- ETL: не исполнять код из CSV/HTML; quarantine (см. data-quality-etl).

### 3.4 Frontend (React)

- Не использовать `dangerouslySetInnerHTML` без санитизации.
- Не хранить staff-токены в `localStorage` (v1 public — без JWT).
- `fetch` на API: credentials только если нужно; CSRF для cookie-POST.
- Нет open redirect с `?next=` без allowlist.
- Зависимости npm: lockfile; не подключать произвольный third-party JS без SRI/нужды.
- Метрика/аналитика — после cookie consent (CSP учёт).

### 3.5 Infra (итерация 5, заложить в конфиги заранее)

- TLS 1.2+; HSTS после стабилизации.
- CSP (default-src/script-src/style-src/img-src/connect-src) — без ослабления
  «ради SEO» (БЗ веб-стек).
- Postgres/Redis не наружу; только docker network / localhost.
- SMTP: TLS, пароль ящика в env; SPF/DKIM/DMARC на домене.
- Бэкапы без публичного ACL; секреты не в образе Docker.

---

## 4. Встраивание в итерации

| Итерация | Security-задачи (чекбокс в работе) |
|----------|-------------------------------------|
| **0–1** | SECRET_KEY fail-closed; `.env.example`; CORS whitelist; нет raw SQL; pip-audit локально |
| **2** | Media upload validate; раздача PDF без directory listing |
| **3** | Lead: validate + honeypot + throttle; маскировка PII в логах Celery |
| **4** | CSP headers (draft); нет DOM XSS; consent для Метрики |
| **5** | `check --deploy`; TLS/HSTS; CSP prod; nginx admin harden; CI pip-audit + npm audit |
| **Всегда** | чеклист стандартов перед коммитом/деплоем; ruff; mypy |

---

## 5. Автоматика CI (минимум)

```text
ruff check / format --check
mypy (scope backend)
pytest (вкл. security-сценарии: throttle, honeypot, no price leak)
pip-audit
npm audit --omit=dev  (или аналог; не игнорировать critical)
frontend build
```

Опционально позже: bandit, Dependabot/Renovate.

---

## 6. Тесты безопасности (примеры контрактов)

- `GET` SKU без `show_prices` → в JSON нет суммы / есть `price_on_request`.
- `POST /api/leads/` без обязательных полей → 400; honeypot заполнен → 201
  без создания **или** silent drop (зафиксировать одно поведение).
- `POST /api/leads/` > N/мин с IP → 429.
- Не-staff → 403 на write Admin/API.
- Upload `.exe` / path `../` → 400.
- Prod settings: `manage.py check --deploy` без критичных WARN
  (на staging с prod-like env).

---

## 7. Чеклист разработчика (каждый PR)

Скопировано/адаптировано из БЗ §8 + специфика проекта:

- [ ] Нет секретов в diff; `.env` не добавлен
- [ ] Ввод через serializer/формы; ORM only
- [ ] Нет `eval` / `pickle` / `shell=True` с user input
- [ ] Новые POST — throttle или явный skip с обоснованием
- [ ] Логи без телефонов/email целиком (маска)
- [ ] Цены не утекли в публичный serializer
- [ ] `poetry run pip-audit` / CI green
- [ ] Для UI: нет `dangerouslySetInnerHTML` на user/CMS HTML без sanitize

Полный pre-deploy: стандарты разработки (чеклист коммита/деплоя) +
[infra-reg-ru.md](infra-reg-ru.md) cutover.

Перед каждым коммитом: `./scripts/pre-commit-checkup.sh`.

---

## 8. Связь с другими docs

| Документ | Пересечение |
|----------|-------------|
| [data-quality-etl.md](data-quality-etl.md) | A08 integrity данных |
| [infra-reg-ru.md](infra-reg-ru.md) | TLS, SMTP, секреты на VPS |
| [seo-url-migration.md](seo-url-migration.md) | open redirect / canonical allowlist |
| [readiness-backend-ux.md](readiness-backend-ux.md) | CSP vs SEO |
