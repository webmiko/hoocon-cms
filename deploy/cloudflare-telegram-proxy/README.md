# Cloudflare Worker — Telegram Bot API proxy

VPS (reg.ru MSK) often cannot reach `api.telegram.org`, and Telegram may not
reach the VPS either. This Worker covers both directions:

1. **Outbound** (Django → Telegram):
   `https://hoocon-telegram-api.npok9.workers.dev/bot<TOKEN>/<method>`
   → `https://api.telegram.org/bot<TOKEN>/<method>`
2. **Inbound** (Telegram → Django):
   `…/webhook` → `WEBHOOK_FORWARD_URL` (prod Admin webhook)

## Deploy

```bash
cd deploy/cloudflare-telegram-proxy
npx wrangler login
npx wrangler deploy
printf '%s' 'https://hoocon.ru/api/integrations/telegram/webhook/' \
  | npx wrangler secret put WEBHOOK_FORWARD_URL
```

Optional IP allowlist for **outbound** `/bot…` only (VPS public IP):

```bash
npx wrangler secret put ALLOWED_IPS
```

## Prod `.env`

```bash
TELEGRAM_API_BASE=https://hoocon-telegram-api.npok9.workers.dev
```

## setWebhook

Point Bot API webhook at the Worker (same `secret_token` as Django):

`https://hoocon-telegram-api.npok9.workers.dev/webhook`

Restart `web` + `celery_worker` after changing env.
