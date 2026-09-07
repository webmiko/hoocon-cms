# Cloudflare Worker — Telegram Bot API proxy

VPS (reg.ru MSK) often cannot reach `api.telegram.org`. This Worker proxies:

`https://hoocon-telegram-api.npok9.workers.dev/bot<TOKEN>/<method>`
→ `https://api.telegram.org/bot<TOKEN>/<method>`

## Deploy

```bash
cd deploy/cloudflare-telegram-proxy
npx wrangler login
npx wrangler deploy
```

Optional IP allowlist (VPS public IP):

```bash
npx wrangler secret put ALLOWED_IPS
# paste: 1.2.3.4
```

## Prod `.env`

```bash
TELEGRAM_API_BASE=https://hoocon-telegram-api.npok9.workers.dev
```

Restart `web` + `celery_worker` after changing env.
