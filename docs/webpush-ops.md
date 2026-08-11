# Web Push (PWA) — ops

Уведомления в браузере / установленном PWA: чат поддержки (staff + посетитель)
и маркетинговые рассылки из Admin.

## Ключи VAPID

На машине с Poetry (из `backend/`):

```bash
poetry run vapid --gen
```

В `.env` на VPS (и локально для тестов):

```bash
WEBPUSH_VAPID_PUBLIC_KEY=<url-safe applicationServerKey>
WEBPUSH_VAPID_PRIVATE_KEY=<private>
WEBPUSH_VAPID_SUBJECT=mailto:noreply@hoocon.ru
```

После правки `.env` — recreate `web` + `celery_worker` (compose hub).

**Не коммитить** private key.

Проверка: `GET /api/webpush/vapid-public-key/` → `{"configured": true, ...}`.

## Браузерный push-сервис

Подписка (`PushManager.subscribe`) идёт **не на наш VPS**, а в push-сервис
браузера:

| Браузер | Сервис |
|---------|--------|
| Chrome / Edge / Android | Google FCM |
| Firefox | Mozilla Autopush |
| Safari (iOS) | Apple — обычно только после «На экран „Домой“» (PWA) |

Если UI пишет «Push-сервис браузера недоступен» /
`AbortError: push service not available`:

- встроенный браузер Cursor / Electron — push часто нет, это нормально;
- Chrome без доступа к FCM (сеть / регион / без Google services) — попробуйте
  Firefox или установленный PWA;
- iOS Safari без PWA — установите сайт на Домой, затем включите снова.

VAPID на сервере при этом может быть `configured: true` — ключи наши в
порядке, падает именно клиентский push endpoint.

## Кто что получает

| Тема | Кто подписывается | Триггер |
|------|-------------------|---------|
| `topic_support` | Staff: Admin → Поддержка → «Push в браузер» | Inbound в чат |
| `topic_support` | Посетитель: виджет → «Уведомлять об ответе» | Ответ менеджера (web) |
| `topic_marketing` | После cookie «Новости» + баннер «Включить» | Admin → Web Push → рассылка |

iOS: push в Safari обычно только после «На экран „Домой“» (PWA). Основной
target v1 — Chrome / Edge / Android (где FCM доступен).

## Persist после reload

`PushSubscription` хранится в браузере (не в React state). После F5:

1. виджет чата вызывает `syncExistingWebPush` и снова POSTit endpoint →
   Django (перепривязка `session_key` / topics);
2. UI показывает «Уведомления включены», без повторного запроса permission;
3. `unsubscribe()` вызывается только при явной смене VAPID-ключа, не при
   обычной ошибке сети.

## Admin

- Список подписок: **Web Push**
- Рассылка: changelist → **Push-рассылка** (заголовок, текст, URL)
