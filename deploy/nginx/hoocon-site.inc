# Shared site body for HTTP (IP break-glass) and HTTPS (apex).
# Included from hoocon.conf — do not enable as a standalone site.

client_max_body_size 20M;  # matches MAX_PRODUCT_FILE_SIZE_BYTES (PDF upload)

# Frontend SPA root (built in Iter 4; stub for now).
root /var/www/hoocon/frontend/dist;
index index.html;

# Security headers (CSP tightened in Iter 5; baseline now).
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
# CSP / HSTS — enable HSTS after TLS cutover stabilizes (docs/infra-reg-ru.md §5.3).
# add_header Content-Security-Policy "default-src 'self'; object-src 'none'; frame-ancestors 'none';" always;
# add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Active Redirect rows → 301 (Django RedirectMiddleware remains fallback).
if ($hoocon_redirect != "") {
    return 301 $hoocon_redirect;
}

# API proxy → Django (gunicorn).
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Public read-only JSON — the only /api/ subtrees we compress. Opt-in, not
# opt-out: /api/csrf/ hands out a CSRF token and /api/support/ carries chat
# bodies, so a blanket `gzip on` under /api/ would put a secret and reflected
# input in the same compressed response. Catalog and content are anonymous GETs
# with no secret, and they are the big payloads (skus ~32 KiB, pages ~46 KiB).
# These blocks duplicate the /api/ proxy setup because a longer prefix wins
# outright in nginx — keep limit_req and the proxy headers in sync with it.
location /api/catalog/ {
    limit_req zone=api_limit burst=20 nodelay;

    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types application/json;
    # B2B clients often sit behind corporate proxies, which send Via; the
    # default (off) would ship these responses raw to exactly those users.
    gzip_proxied any;

    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /api/content/ {
    limit_req zone=api_limit burst=20 nodelay;

    gzip on;
    gzip_vary on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types application/json;
    gzip_proxied any;

    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Lead submission — stricter rate limit (Iter 3 throttle + nginx backstop).
location /api/leads/ {
    limit_req zone=lead_limit burst=3 nodelay;
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Django Admin — IP allowlist (see admin-allow.conf.example).
# Copy example → /etc/nginx/admin-allow.conf, set allow IPs, then uncomment.
location /admin/ {
    # include /etc/nginx/admin-allow.conf;
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# Media (uploaded PDF/images) — no directory listing, no script execution.
# Hotlink: allow empty Referer (direct open / mail) + our hosts; deny foreign embeds.
# Keep host list in sync with DJANGO_ALLOWED_HOSTS / MEDIA_HOTLINK_EXTRA_HOSTS.
location /media/ {
    # server_names covers hoocon.ru / www / IP from server_name; do not
    # repeat those names here (nginx "conflicting parameter").
    valid_referers
        none
        blocked
        server_names
        localhost
        127.0.0.1
        ~(?i)^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?(/|$)
        ~(?i)^https?://161\.104\.19\.49(:[0-9]+)?(/|$)
        ~(?i)^https?://([^/]+\.)?hoocon\.ru(:[0-9]+)?(/|$);

    if ($invalid_referer) {
        return 403;
    }

    autoindex off;
    alias /var/www/hoocon/media/;
    expires 7d;
    add_header Cache-Control "public, max-age=604800" always;
    add_header X-Content-Type-Options "nosniff" always;
    # PDF inline viewing allowed; no inline scripts.
    add_header Content-Disposition "inline";
}

# gzip_types stays inside the static locations on purpose. nginx.conf enables
# gzip globally but its default gzip_types is text/html, so proxied HTML was
# compressed while /assets/*.css|js shipped raw (~454 KiB) and starved the hero
# WebP of bandwidth (mobile LCP load delay 870 ms). Declaring the types here
# leaves HTML/API encoding exactly as before — no new BREACH surface on
# CSRF-bearing responses. woff2 is already compressed; keep it out of the list.

# Django collectstatic — long cache (hashed filenames when ManifestStaticFiles).
location /static/ {
    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/css text/javascript text/plain application/javascript
               application/json image/svg+xml;

    alias /var/www/hoocon/staticfiles/;
    expires 30d;
    add_header Cache-Control "public, max-age=2592000, immutable" always;
    add_header X-Content-Type-Options "nosniff" always;
}

# Vite hashed bundles (JS/CSS/fonts under /assets/*-[hash].*) — immutable.
location /assets/ {
    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/css text/javascript text/plain application/javascript
               application/json image/svg+xml;

    expires 1y;
    add_header Cache-Control "public, max-age=31536000, immutable" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    try_files $uri =404;
}

# Service worker: never cache. A stale sw.js keeps the previous app shell.
location = /sw.js {
    add_header Cache-Control "no-cache, no-store, must-revalidate" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    try_files $uri =404;
}

# Public SPA images / logos (no content-hash in filename).
location ~* ^/(?:home|brand|hero)/ {
    expires 30d;
    add_header Cache-Control "public, max-age=2592000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    try_files $uri =404;
}

# Root public wordmarks (stable names; 30d revalidate).
location ~* ^/(?:logo(?:-on-dark)?|favicon|og-image)\.(?:svg|png|ico)$ {
    expires 30d;
    add_header Cache-Control "public, max-age=2592000" always;
    add_header X-Content-Type-Options "nosniff" always;
    try_files $uri =404;
}

# PWA / home-screen icons — short cache (URLs also versioned in manifest).
location ~* ^/(?:pwa-\d+|apple-touch-icon)\.(?:png|ico)$ {
    expires 1d;
    add_header Cache-Control "public, max-age=86400, must-revalidate" always;
    add_header X-Content-Type-Options "nosniff" always;
    try_files $uri =404;
}

location = /manifest.webmanifest {
    expires 1d;
    add_header Cache-Control "public, max-age=86400" always;
    try_files $uri =404;
}

# robots / sitemap / llms from Django.
location = /robots.txt {
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /sitemap.xml {
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}
location = /llms.txt {
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

# SPA: canonical without trailing slash; /index.html → /; HTML via Django SEO head.
location = /index.html {
    return 301 /$is_args$args;
}

location / {
    rewrite ^/(.*)/$ /$1 permanent;
    try_files $uri @spa;
}

location @spa {
    proxy_pass http://hoocon_app;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
