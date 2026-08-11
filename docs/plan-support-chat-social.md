# План: чат поддержки — виджет сайта + Telegram / VK / MAX

Дата: 2026-07-20  
Обновлено: 2026-08-11 (ship web + Admin + Telegram; VK/MAX — следующий PR)  
Статус: **в работе / частично shipped** — web виджет + Admin inbox + Telegram;
VK/MAX adapters — после токенов в SiteSettings.  
Цель: единый inbox в Admin; клиент пишет с **виджета на сайте** и/или из
мессенджеров (TG / VK / MAX); менеджер отвечает в одном месте; чат живой
по **настраиваемому рабочему расписанию**.

Связь: интеграции ботов уже в SiteSettings; анонсы — `social.SocialPost`.
Чат — отдельный app `supportchat` (диалоги ≠ broadcast).

Не в scope: корзина, Stripe, ЛК дилера с остатками, WhatsApp (отдельный план).
Клиентская регистрация (пароль / OTP / Яндекс) — [plan-client-auth.md](plan-client-auth.md).
Клиентский ЛК (КП / статусы; обращения из чата — фаза 2) —
[plan-client-cabinet.md](plan-client-cabinet.md); в очереди после auth,
чат (#3) кормит обращения в ЛК.

Admin: раздел **«Поддержка»** (inbox диалогов сайта + каналов соцсетей).

---

## 0. Гейт старта (обязательно)

Код чата **не начинаем**, пока на prod не готово:

| # | Условие | Зачем |
|---|---------|--------|
| 1 | VPS reg.ru, домен, **HTTPS** (TLS) | Webhooks мессенджеров + cookie CSRF виджета |
| 2 | Почта SMTP (заявки / опц. notify о чате) | Уже в Iter 5; тот же стек |
| 3 | Celery + Redis на VPS | Outbound reply + тяжёлые webhook |
| 4 | Токены TG/VK/MAX в Admin или `.env` | Уже модель есть |

Локальная разработка виджета возможна раньше; **webhooks трёх сетей** —
только на HTTPS URL.

---

## 1. Зачем (боль)

- RFQ односторонние; уточнения уходят в мессенджеры вне CMS.
- Три кабинета мессенджеров + сайт — дорого для 1–3 менеджеров.
- Нужен **один Admin-inbox** + удобный вход с сайта (виджет), без ожидания
  «сначала только Telegram».

---

## 2. Продуктовое решение

### 2.1. Роли и каналы

| Кто | Канал | Где пишет |
|-----|--------|-----------|
| Клиент | `web` | Виджет на сайте (React) |
| Клиент | `telegram` / `vk` / `max` | Личный чат с ботом |
| Менеджер | Admin | Единая лента диалогов + ответ |
| Система | Webhook / API | Нормализация → `Message` |

Все четыре канала видны менеджеру одинаково (бейдж канала).

### 2.2. Виджет на сайте (в scope первого ship)

Плавающая кнопка → панель чата:

1. Короткое приветствие + опц. имя / email / компания (мягкая валидация).
2. Лента сообщений (текст в MVP).
3. Поле ввода + отправка.
4. Параллельно: кнопки «Продолжить в Telegram / VK / MAX» (deep link),
   чтобы не терять тех, кто предпочитает мессенджер.

Технически виджет:

- Session cookie (анонимная `support_session_id`) + CSRF (`/api/csrf/`).
- Public API под throttle (как leads): создать/продолжить диалог, post
  message, poll новых сообщений (SSE или short polling; WebSocket — later).
- Канал Conversation = `web`.
- Не светить чужие диалоги (IDOR: только своя session).
- Учитывать **расписание** (§2.4): outside hours — принять сообщение в очередь
  + показать «Мы ответим в рабочее время» (не блокировать запись в БД).

### 2.3. Admin UX (раздел «Поддержка»)

В боковом меню Admin — пункт **«Поддержка»**: единая лента диалогов
с сайта и из подключённых соцсетей (TG / VK / MAX).

```
┌─────────────────┬──────────────────────────────────────────┐
│ Диалоги         │  Web · Иван · не прочитано               │
│ ● Web Иван  2м  │  ─────────────────────────────────────── │
│   TG Мария      │  [клиент] Здравствуйте, нужен КП…        │
│   VK ООО …      │  [менеджер] Добрый день! Уточните DN…    │
│   MAX Петр      │  ─────────────────────────────────────── │
│ Фильтр: канал   │  [________ответ________________] [Отпр.] │
│ непрочитанные   │  Client / Lead / Assignee                 │
└─────────────────┴──────────────────────────────────────────┘
```

Unread badge в nav Admin (как Lead sticker). Reply → Celery → publisher
канала (web: просто запись Message + виджет подхватывает poll).

### 2.4. Рабочее расписание (в scope первого ship)

Чат **работает по расписанию**. Настройка в Admin (блок «Поддержка →
расписание» или fieldset в SiteSettings / `supportchat`):

| Режим | Что задаётся |
|-------|----------------|
| **По дням недели** | Пн…Вс **по отдельности**: день выкл / интервал(ы) `HH:MM–HH:MM` |
| **Шаблон будни** | Одна кнопка «применить к Пн–Пт» (копирует интервалы) |
| **Шаблон выходные** | «применить к Сб–Вс» |
| **Часовой пояс** | Явно (по умолчанию `Europe/Moscow` / `TIME_ZONE` проекта) |
| **Праздники (later)** | Список дат «закрыто» — не в v1, задел в модели |

**Дефолт при миграции / первом seed** (можно менять в Admin):

| Дни | Интервал |
|-----|----------|
| Пн–Чт | 09:00–18:00 |
| Пт | 09:00–17:00 |
| Сб–Вс | выходной (`is_closed`) |

Поведение вне часов:

| Поверхность | Поведение |
|-------------|-----------|
| Виджет | Принимает сообщение; статус `outside_hours`; текст автоответа из настроек |
| Мессенджеры | То же: сообщение в inbox; опц. автоответ ботом (один шаблон) |
| Admin | Диалоги видны всегда; badge «вне часов» на новых |
| API `/channels/` / `/schedule/` | `is_open_now`, `next_open_at`, `timezone` (без секретов) |

Несколько интервалов в день (обеденный перерыв) — **да** в v1
(список пар start/end на день).

---

## 3. Архитектура

### 3.1. Контуры

| Контур | App / модели | Направление |
|--------|--------------|-------------|
| Анонсы | `social.SocialPost` | сайт → канал (broadcast) |
| Чат | `supportchat.*` | клиент ↔ (виджет \| бот) ↔ Admin |

Общее: credentials SiteSettings, расширенные publishers для private reply.

### 3.2. Модели

**Conversation** — `channel` ∈ {web, telegram, vk, max}; unique
`(channel, external_user_id)` для мессенджеров; для web —
`(channel, session_key)`.

Поля: display_name, contact_email (опц.), status, assignee, client, lead,
last_message_at, unread / seen_at, timestamps.

**Message** — direction inbound/outbound; body; external_message_id
(идемпотентность webhook); author (staff outbound); status; raw_payload
JSONB (TTL); created_at.

**ClientExternalIdentity** (или JSON на Client) — связка channel +
external_user_id → CRM.

### 3.2.1. Расписание (модели)

Вариант A (рекомендуемый): singleton рядом с чатом —

```
SupportSchedule          # timezone, auto_reply_outside_hours (text)
SupportScheduleDay       # weekday 0=Mon…6=Sun, is_closed: bool
SupportScheduleInterval  # day FK, start_time, end_time (несколько на день)
```

Вариант B: JSONField на SiteSettings — быстрее старт, хуже валидация в Admin.

Рекомендация: **вариант A** + Admin UI с таблицей 7 дней и кнопками
«Заполнить будни» / «Заполнить выходные» (копируют интервалы с шаблона
формы, не отдельные сущности «будни»).

Сервис: `supportchat.schedule.is_open_now(at: datetime | None) -> bool` и
`next_open_at(...)` — единственная точка правды для виджета и webhook.

### 3.3. Потоки

**Виджет → Admin**

```
SPA widget → POST /api/support/messages/ (CSRF + throttle)
  → get_or_create Conversation(web, session)
  → Message inbound
  → badge / опц. email менеджеру
Admin reply → Message outbound → widget poll/SSE
```

**Мессенджер → Admin**

```
Webhook TG|VK|MAX → verify → adapter → Conversation + Message
Admin reply → Celery → bot API private message
```

### 3.4. Webhooks

| Канал | Endpoint |
|--------|----------|
| Telegram | `POST /api/support/webhooks/telegram/` |
| VK | `POST /api/support/webhooks/vk/` |
| MAX | `POST /api/support/webhooks/max/` |

Секреты в env / SiteSettings. Nginx rate limit. Не long-poll в gunicorn.

### 3.5. Public API виджета (whitelist)

| Метод | Path | Назначение |
|-------|------|------------|
| POST | `/api/support/conversations/` | старт / resume по session |
| GET | `/api/support/conversations/current/messages/` | лента своей session |
| POST | `/api/support/conversations/current/messages/` | исходящее от клиента |
| GET | `/api/support/channels/` | какие мессенджеры включены + deep links |
| GET | `/api/support/schedule/` | `is_open_now`, `timezone`, `next_open_at`, дни (без PII) |
| — | list чужих диалогов | **запрещено** |

Токены ботов в API **не** отдаём (только публичные deep-link URL / username).

---

## 4. Безопасность

| Риск | Контроль |
|------|----------|
| Подделка webhook | secret_token / VK secret / MAX signature |
| IDOR виджета | только session владельца |
| Спам виджета | throttle + honeypot опц. + длина body |
| Спам webhook | rate limit IP + per user id |
| XSS Admin / widget | escape; без raw HTML от клиента |
| PII в логах | как leads |
| Вложения | **текст only** в первом ship; файлы — later |

Дополнить [security-baseline.md](security-baseline.md).

---

## 5. Итерации разработки (после гейта §0)

Один shipable релиз «чат v1» = виджет + Admin + **три** мессенджера.
Внутри — короткие срезы, но **не** отдельный прод-релиз «только TG».

### Slice A — ядро (2–3 д)

- [ ] App `supportchat`: Conversation, Message, migrations
- [ ] **SupportSchedule** + дни + интервалы; Admin UI + шаблоны будни/выходные
- [ ] Seed дефолта: Пн–Чт 09–18, Пт 09–17, Сб–Вс закрыто
- [ ] `is_open_now` / `next_open_at` + тесты границ (Пт 17:00, выходной, полночь)
- [ ] Admin inbox + reply (канал-агностичный)
- [ ] Unread badge
- [ ] Тесты моделей / Admin auth

### Slice B — виджет сайта (2–3 д)

- [ ] Public API + session + CSRF + throttle
- [ ] React виджет (кнопка + панель + poll) + индикатор «сейчас открыто/закрыто»
- [ ] Автоответ / баннер вне часов (текст из настроек)
- [ ] Deep links блок «или напишите в …»
- [ ] Тесты API IDOR / throttle / no token leak / schedule public

### Slice C — три мессенджера (3–5 д)

- [ ] Adapters + webhooks TG, VK, MAX параллельно
- [ ] Outbound private reply publishers
- [ ] Вне часов: сохранить inbound + опц. автоответ в мессенджер
- [ ] setWebhook / Callback на prod URL
- [ ] Тесты idempotency / bad secret → 403

### Slice D — CRM / UX (1–2 д)

- [ ] ClientExternalIdentity + опц. привязка Lead
- [ ] «Создать заявку из диалога»
- [ ] Документация ops (webhooks, deep links)
- [ ] security-baseline § chat

**Критерий готово v1:** клиент пишет с виджета **и** из TG/VK/MAX → всё в
одном Admin → ответ доходит в исходный канал.

### Later (не блокирует v1)

- Вложения, шаблоны быстрых ответов менеджера, SLA stats, WebSocket,
  праздничные даты «закрыто», AI-автоответы.

---

## 6. URL inventory

| Path | Кто |
|------|-----|
| `/api/support/webhooks/{telegram,vk,max}/` | мессенджеры |
| `/api/support/conversations/…` | виджет (anon + session) |
| `/api/support/channels/` | виджет (публичные deep links) |
| `/api/support/schedule/` | виджет (открыто ли сейчас) |
| `/admin/supportchat/conversation/` | staff |
| `/admin/supportchat/supportschedule/` | staff — расписание |
| OpenAPI docs | webhooks/schema — staff-only на prod |

---

## 7. Тест-план (минимум)

| Кейс | Ожидание |
|------|----------|
| Webhook без secret | 403 |
| Дубликат external_message_id | без второго Message |
| Виджет: чужой conversation id | 404/403 |
| Виджет throttle | 429 |
| Public channels | нет bot token |
| Admin anon | 302 |
| Reply web / TG / VK / MAX | Message sent + доставка (mock HTTP) |
| Дефолт: Пн–Чт 09–18, сейчас Вт 10:00 MSK | `is_open_now=True` |
| Дефолт: Пт 17:30 | `is_open_now=False` (Пт до 17:00) |
| Дефолт: Сб закрыт | `is_open_now=False`, `next_open_at` = Пн 09:00 |
| День с двумя интервалами (обед) | вне обеда → closed |
| Шаблон «будни» в Admin | Пн–Пт получают те же интервалы |
| Вне часов: post в виджет | 201, Message + outside_hours / автоответ |

---

## 8. Зависимости

| Зависимость | Статус |
|-------------|--------|
| Iter 5: VPS, HTTPS, домен, SMTP | ✅ |
| Токены SiteSettings | ✅ TG; VK/MAX — pending |
| Celery/Redis prod | ✅ |
| CSP / cookie для виджета | учесть при CSP prod |

Слот: **после Iter 5**, в рамках усиления (Iter 6) — приоритетный блок
«чат поддержки».

---

## 9. Решения (согласовано 2026-07-20, v3)

| Вопрос | Решение |
|--------|---------|
| Когда код | **После** выгрузки на VPS: HTTPS + домен + почта |
| Виджет на сайте | **Да**, в первом ship |
| Каналы мессенджеров | **Сразу все три**: Telegram + VK + MAX |
| Deep links из виджета | Да (параллельно с web-чатом) |
| Один bot token на анонсы+чат | Да |
| Admin inbox | Единый на web + TG + VK + MAX |
| **Рабочее расписание** | **Да**, в первом ship |
| Расписание: гранулярность | **Каждый день недели отдельно** + кнопки шаблонов будни/выходные |
| **Дефолт расписания** | Пн–Чт 09:00–18:00; Пт 09:00–17:00; Сб–Вс выходной |
| Несколько слотов в день | **Да** (напр. 09–13 и 14–18) |
| Часовой пояс | Явный в настройках (default = `TIME_ZONE` проекта) |
| Вне часов | Сообщения **принимаем**; клиенту — статус/автоответ; в Admin — inbox |
| Праздники | Не в v1 (задел) |
| Вложения в v1 | Нет (только текст) |
| WebSocket в v1 | Нет (poll / SSE) |
| Кто видит чаты | все staff |

---

## 10. Критерии приёмки

1. Виджет на prod-сайте создаёт диалог; менеджер отвечает из Admin; клиент
   видит ответ в виджете.
2. Сообщения из TG, VK и MAX попадают в тот же inbox; ответы уходят в
   исходный канал.
3. Нет утечки токенов/чужих переписок в публичный API.
4. Webhooks идемпотентны; без secret — 403.
5. Документация ops + security-baseline обновлены.
6. Расписание: каждый день настраивается; шаблоны будни/выходные работают;
   виджет и боты показывают корректный статус «открыто/закрыто»; вне часов
   сообщения сохраняются с автоответом.

---

## 11. Вне scope

- ChatGPT-автоответы, WhatsApp, email-omnichannel в том же inbox.
- Клиентский ЛК с архивом — отдельный план
  [plan-client-cabinet.md](plan-client-cabinet.md) (очередь #2 после auth;
  диалоги чата — фаза 2 ЛК).
- Замена RFQ (заявки остаются).
