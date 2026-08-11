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

## Кто что получает

| Тема | Кто подписывается | Триггер |
|------|-------------------|---------|
| `topic_support` | Staff: Admin → Поддержка → «Push в браузер» | Inbound в чат |
| `topic_support` | Посетитель: виджет → «Уведомлять об ответе» | Ответ менеджера (web) |
| `topic_marketing` | После cookie «Новости» + баннер «Включить» | Admin → Web Push → рассылка |

iOS: push в Safari обычно только после «На экран „Домой“» (PWA). Основной
target v1 — Chrome / Edge / Android.

## Admin

- Список подписок: **Web Push**
- Рассылка: changelist → **Push-рассылка** (заголовок, текст, URL)
