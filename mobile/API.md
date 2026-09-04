# Staff API OpenAPI draft — Hoocon Manager

Base: `https://hoocon.ru/api/staff/`  
Auth after login: `Authorization: Token <key>`  
Feature flag: `STAFF_API_ENABLED=true`

## Auth

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/auth/otp/start/` | `{ "login": "email" }` | `{ "ok": true, "challenge_id": "...", "email_masked": "a***@…" }` |
| POST | `/auth/otp/verify/` | `{ "challenge_id", "code" }` | `{ "token", "user": {…} }` |
| POST | `/auth/otp/resend/` | `{ "challenge_id" }` | `{ "ok": true }` |
| POST | `/auth/logout/` | — | `{ "ok": true }` |
| GET | `/me/` | — | user + groups + `sees_all_leads` |

## Badges

| GET | `/badges/` | `{ "leads_new": int, "support_unread": int }` |

## Leads

| GET | `/leads/?status=&page=` | paginated list |
| GET | `/leads/{id}/` | detail |
| POST | `/leads/{id}/take/` | take in work → 409 if taken |
| POST | `/leads/{id}/status/` | `{ "status": "in_progress"|"done" }` |

## Clients

| GET | `/clients/?q=&page=` | list |
| GET | `/clients/{id}/` | detail + recent activities/emails |
| POST | `/clients/{id}/activities/` | `{ "activity_type", "subject", "body" }` |
| POST | `/clients/{id}/emails/` | `{ "subject", "body", "to_email?", "send_now?" }` |

## Support

| GET | `/conversations/?status=` | list (`title`, `company`, `phone`, …) |
| GET | `/conversations/{id}/` | detail (same party fields) |
| DELETE | `/conversations/{id}/` | удалить, только если `client_id` пуст (204 / 400) |
| GET | `/conversations/{id}/messages/?after=` | messages |
| POST | `/conversations/{id}/messages/` | `{ "body" }` |
| POST | `/conversations/{id}/assign/` | claim |
| POST | `/conversations/{id}/close/` | close |
| POST | `/conversations/{id}/read/` | clear unread |

`title` / `display_name` — подпись хаба: «Имя · Компания» или «Пользователь · телефон/email»
(не канал «Сайт»). Канал — в `channel_label`.

## Devices (FCM)

| POST | `/devices/` | `{ "fcm_token", "platform": "android"|"ios" }` |
| DELETE | `/devices/{id}/` | unregister |

## Errors

JSON `{ "detail": "…" }` or `{ "ok": false, "error": "…" }` with 4xx.
