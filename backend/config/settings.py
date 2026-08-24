"""Django settings for Hoocon CMS."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

from config.media_hotlink import build_media_hotlink_hosts
from config.release import RELEASE_VERSION, release_label
from config.static_urls import versioned_static

# Load project-root .env; do not call load_dotenv() twice (avoid CWD-anchored
# overrides pulling in an unexpected file).
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, *, default: bool) -> bool:
    """Read env var as bool; return default if unset or unrecognized."""
    raw = os.getenv(name, "").lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    return default


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-in-local-env-only",
)
# Fail closed: require explicit DJANGO_DEBUG=True for local; prod omits it.
DEBUG = _env_bool("DJANGO_DEBUG", default=False)

# Local QA: show CMS items with published_at in the future (articles/news).
# Prod must keep False so staggered go-live stays hidden until the date.
CONTENT_SHOW_SCHEDULED = _env_bool("CONTENT_SHOW_SCHEDULED", default=False)

if not DEBUG and (not SECRET_KEY or SECRET_KEY.startswith("django-insecure")):
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY in the environment when DJANGO_DEBUG=False",
    )

if DEBUG and SECRET_KEY.startswith("django-insecure"):
    import warnings

    warnings.warn(
        "DJANGO_SECRET_KEY is the insecure default — set a real key before any shared env.",
        UserWarning,
        stacklevel=1,
    )

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]

# Prod hardening (enable via env on VPS; see docs/security-baseline.md).
if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"
    CSRF_COOKIE_SAMESITE = "Lax"
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = _env_bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
    # COOP needs a trustworthy origin (HTTPS). On http://IP the browser ignores
    # the header and Lighthouse logs a console error. Default off until TLS;
    # then set DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY=same-origin.
    _coop = os.getenv("DJANGO_SECURE_CROSS_ORIGIN_OPENER_POLICY", "none").strip()
    SECURE_CROSS_ORIGIN_OPENER_POLICY = None if _coop.lower() in ("", "none", "off") else _coop
    if _env_bool("DJANGO_BEHIND_HTTPS_PROXY", default=True):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

_DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ALLOWED_ORIGINS = [
    origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", _DEFAULT_CORS).split(",") if origin.strip()
]
CORS_ALLOW_CREDENTIALS = False

# Trusted origins for CSRF (admin login POST from SPA dev server / prod domain).
# Spec: security-baseline §CORS/CSRF; ПЛАН §6 Iter 4 — F8.
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.getenv("CSRF_TRUSTED_ORIGINS", _DEFAULT_CORS).split(",") if origin.strip()
]

# Hotlink: foreign <img src="https://ours/media/..."> gets 403 (Referer allowlist).
# Empty Referer allowed (direct tab, mail PDF). Prod nginx mirrors this — see
# deploy/nginx/hoocon.conf. Disable with MEDIA_HOTLINK_ENABLED=false.
MEDIA_HOTLINK_ENABLED = _env_bool("MEDIA_HOTLINK_ENABLED", default=True)
MEDIA_HOTLINK_ALLOW_EMPTY_REFERER = _env_bool(
    "MEDIA_HOTLINK_ALLOW_EMPTY_REFERER",
    default=True,
)
_MEDIA_HOTLINK_EXTRA = [host.strip() for host in os.getenv("MEDIA_HOTLINK_EXTRA_HOSTS", "").split(",") if host.strip()]
MEDIA_HOTLINK_ALLOWED_HOSTS = build_media_hotlink_hosts(
    allowed_hosts=ALLOWED_HOSTS,
    cors_origins=[*CORS_ALLOWED_ORIGINS, *CSRF_TRUSTED_ORIGINS],
    extra_hosts=_MEDIA_HOTLINK_EXTRA,
)

INSTALLED_APPS = [
    # django-unfold must precede django.contrib.admin (template/override order).
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "django_filters",
    "django_celery_beat",
    "drf_spectacular",
    "rest_framework",
    # Brute-force protection for admin login (ПЛАН §6 Iter 1).
    "axes",
    # Project apps (с итерации 1)
    "accounts.apps.AccountsConfig",
    "redirects.apps.RedirectsConfig",
    "sitesettings",
    "catalog.apps.CatalogConfig",
    "content",
    "leads",
    "crm.apps.CrmConfig",
    "search",
    "social",
    "supportchat.apps.SupportchatConfig",
    "webpush.apps.WebpushConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
]
if DEBUG:
    MIDDLEWARE.append("django.middleware.gzip.GZipMiddleware")
MIDDLEWARE.extend(
    [
        "corsheaders.middleware.CorsMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        # Block foreign-site <img>/<embed> of /media/ (DEBUG media + any proxied path).
        "config.media_hotlink_middleware.MediaHotlinkMiddleware",
        # SEO redirects before CommonMiddleware so typo/legacy paths never hit views.
        "redirects.middleware.RedirectMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "axes.middleware.AxesMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
        # Phase 0 bot-load: short Redis/LocMem cache for catalog GET JSON
        # (before CSP so cached responses still get CSP headers).
        "catalog.middleware.CatalogHttpCacheMiddleware",
        "config.csp_middleware.CspMiddleware",
    ],
)

# django-axes: brute-force protection for admin login.
# Spec: docs/security-baseline.md §3.2; ПЛАН §6 Iter 1.
# Lock out an IP after N failed logins within the reset window.
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = int(os.getenv("AXES_COOLOFF_TIME", "1"))  # hours
AXES_LOCKOUT_PARAMETERS = [["ip_address"]]
AXES_RESET_ON_SUCCESS = True
AXES_VERBOSE = _env_bool("DJANGO_DEBUG", default=False)
# Trust one reverse-proxy hop (nginx) for client IP.
AXES_IPWARE_PROXY_COUNT = int(os.getenv("AXES_IPWARE_PROXY_COUNT", "1"))
AXES_IPWARE_META_PRECEDENCE_ORDER = [
    "HTTP_X_FORWARDED_FOR",
    "REMOTE_ADDR",
]
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.static_version",
                "config.context_processors.release_info",
                "config.context_processors.new_leads_sticker",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_use_sqlite = _env_bool("USE_SQLITE", default=False)
_db_name = os.getenv("DB_NAME", "").strip()

if _db_name and not _use_sqlite:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _db_name,
            "USER": os.getenv("DB_USER", "hoocon"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(BASE_DIR / "db.sqlite3"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

# After staff auth (incl. Admin Email OTP) land in Admin, not Django's
# default /accounts/profile/ (SPA shell → empty page on :8000).
LOGIN_REDIRECT_URL = "/admin/"
LOGOUT_REDIRECT_URL = "/admin/login/"

STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATICFILES_DIRS = [BASE_DIR / "static"]
# Dev: WhiteNoise must use Django finders so STATICFILES_DIRS (admin theme) works.
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG
MEDIA_URL = "/media/"
MEDIA_ROOT = str(BASE_DIR / "media")

# Optional deploy SHA for admin CSS/JS cache-bust (?v=); empty → mtime in DEBUG.
BUILD_SHA = os.getenv("BUILD_SHA", "").strip()

# ── django-unfold Admin UI (Hoocon brand; no heavy hoocon-admin.css shell) ─
# Primary scale around brand #dc1313 / hover #b01010 (frontend tokens.css).
_UNFOLD_PRIMARY = {
    "50": "#fef2f2",
    "100": "#fee2e2",
    "200": "#fecaca",
    "300": "#fca5a5",
    "400": "#f87171",
    "500": "#dc1313",
    "600": "#b01010",
    "700": "#8f0d0d",
    "800": "#6e0a0a",
    "900": "#4d0707",
    "950": "#2c0404",
}

UNFOLD = {
    "SITE_TITLE": _("HOOCON CMS"),
    "SITE_HEADER": _("Hoocon"),
    "SITE_SUBHEADER": _("Панель управления"),
    "SITE_URL": "/",
    # Release badge next to branding (e.g. «v0.0.3 beta»).
    "ENVIRONMENT": release_label(),
    # Distinct Admin PWA / home-screen icons (gray + ADMIN; not the public site).
    "SITE_FAVICONS": [
        {
            "href": lambda _r: versioned_static("admin/img/pwa-admin-192.png"),
            "rel": "icon",
            "sizes": "192x192",
            "type": "image/png",
        },
        {
            "href": lambda _r: versioned_static("admin/img/pwa-admin-512.png"),
            "rel": "icon",
            "sizes": "512x512",
            "type": "image/png",
        },
        {
            "href": lambda _r: versioned_static("admin/img/apple-touch-admin.png"),
            "rel": "apple-touch-icon",
            "sizes": "180x180",
            "type": "image/png",
        },
        {
            "href": reverse_lazy("admin-pwa-manifest"),
            "rel": "manifest",
            "type": "application/manifest+json",
        },
    ],
    "COLORS": {
        "primary": _UNFOLD_PRIMARY,
    },
    "STYLES": [
        "config.unfold_callbacks.unfold_extras_css",
    ],
    "SCRIPTS": [
        "config.unfold_callbacks.admin_live_badges_js",
        "config.unfold_callbacks.admin_tables_js",
    ],
    "DASHBOARD_CALLBACK": "config.unfold_callbacks.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Навигация"),
                "separator": True,
                "items": [
                    {
                        "title": _("Панель"),
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    },
                    {
                        "title": _("Заявки"),
                        "icon": "inbox",
                        "link": reverse_lazy("admin:leads_lead_changelist"),
                        "badge": "config.unfold_callbacks.badge_new_leads",
                        "badge_variant": "danger",
                        "badge_style": "solid",
                        "permission": "config.unfold_callbacks.perm_view_lead",
                    },
                    {
                        "title": _("Поддержка"),
                        "icon": "forum",
                        "link": reverse_lazy(
                            "admin:supportchat_conversation_changelist",
                        ),
                        "badge": "config.unfold_callbacks.badge_support_unread",
                        "badge_variant": "danger",
                        "badge_style": "solid",
                        "permission": "config.unfold_callbacks.perm_view_conversation",
                    },
                    {
                        "title": _("Web Push"),
                        "icon": "notifications",
                        "link": reverse_lazy(
                            "admin:webpush_pushsubscription_changelist",
                        ),
                        "permission": "config.unfold_callbacks.perm_view_webpush",
                    },
                    {
                        "title": _("Клиенты"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:crm_client_changelist"),
                        "permission": "config.unfold_callbacks.perm_view_client",
                    },
                    {
                        "title": _("Артикулы"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:catalog_sku_changelist"),
                        "permission": "config.unfold_callbacks.perm_view_sku",
                    },
                    {
                        "title": _("Настройки сайта"),
                        "icon": "settings",
                        "link": reverse_lazy(
                            "admin:sitesettings_sitesettings_changelist",
                        ),
                        "permission": "config.unfold_callbacks.perm_view_sitesettings",
                    },
                ],
            },
        ],
    },
}

# ── SEO / SPA shell (БЗ SEO-индексация-SPA.md) ───────────────────────
SITE_URL = os.getenv("SITE_URL", "https://hoocon.ru").rstrip("/")
_SPA_DEFAULT = str(BASE_DIR.parent / "frontend" / "dist" / "index.html")
SPA_INDEX_HTML = os.getenv("SPA_INDEX_HTML", _SPA_DEFAULT)

# Analytics (fallback if SiteSettings IDs empty; SPA prefers /api/settings/public/).
# Analytics counters (public IDs — not secrets). Admin SiteSettings overrides env.
# Defaults = production counters so CSP / SPA work without empty Admin.
YANDEX_METRIKA_ID = os.getenv("YANDEX_METRIKA_ID", "73321399").strip()
GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "G-DLRV7BZ5JP").strip()

# Social bots (secrets — never expose via API; chat IDs live in SiteSettings Admin).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "").strip()
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()
# Telegram inbound webhook (setWebhook secret_token). Empty = webhook rejects all.
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
# Public deep-link username for 1:1 bot chat in the support widget.
# Default matches production bot; set empty to hide the chip.
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "HooconMsk_bot").strip()
# Public channel for footer / bot menu (t.me/<name>); default official Hoocon channel.
TELEGRAM_CHANNEL_USERNAME = (
    os.getenv(
        "TELEGRAM_CHANNEL_USERNAME",
        "hoocon_moscow",
    )
    .strip()
    .lstrip("@")
)
# /start cover: local file path preferred; else public HTTPS URL for Telegram.
TELEGRAM_WELCOME_PHOTO_PATH = os.getenv("TELEGRAM_WELCOME_PHOTO_PATH", "").strip()
TELEGRAM_WELCOME_PHOTO_URL = os.getenv(
    "TELEGRAM_WELCOME_PHOTO_URL",
    "https://hoocon.ru/og-image.jpg",
).strip()

# Web Push (VAPID). Generate: poetry run vapid --gen && set env on VPS.
WEBPUSH_VAPID_PUBLIC_KEY = os.getenv("WEBPUSH_VAPID_PUBLIC_KEY", "").strip()
WEBPUSH_VAPID_PRIVATE_KEY = os.getenv("WEBPUSH_VAPID_PRIVATE_KEY", "").strip()
WEBPUSH_VAPID_SUBJECT = os.getenv(
    "WEBPUSH_VAPID_SUBJECT",
    "mailto:noreply@hoocon.ru",
).strip()

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "120/min",
        "user": "240/min",
        "lead_create": "10/hour",
        # POST start/send only — keep tight against spam.
        "support_message": "60/hour",
        # GET poll every ~4s needs headroom (15/min); separate from POST scope.
        "support_poll": "120/minute",
        "webpush_subscribe": "30/hour",
        # Telegram retries bursts; keep generous but bounded per IP.
        "telegram_webhook": "120/min",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Hoocon CMS API",
    "DESCRIPTION": "B2B catalog and content API for Hoocon HVAC actuators.",
    "VERSION": RELEASE_VERSION,
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Shared cache for DRF throttles (LocMem is per-worker — weak under Gunicorn).
# Set DJANGO_CACHE_URL=locmem:// in CI (no Redis). Prod: redis://…/2 or omit for default.
_cache_url = os.getenv("DJANGO_CACHE_URL", "").strip()
if _cache_url in {"locmem", "locmem://", "memory"}:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "hoocon-default",
        },
    }
elif not _cache_url and not DEBUG:
    # Prod default: Redis DB 2 (broker 0, results 1).
    _cache_url = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    if _cache_url.endswith("/0"):
        _cache_url = f"{_cache_url[:-2]}/2"
    elif "/0?" in _cache_url:
        _cache_url = _cache_url.replace("/0?", "/2?", 1)
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _cache_url,
        },
    }
elif _cache_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _cache_url,
        },
    }

# Phase 0 bot-load: short GET cache for /api/catalog/{categories,facets,skus}.
# 0 disables. Invalidate on SiteSettings save (prices); else TTL staleness OK.
CATALOG_HTTP_CACHE_SECONDS = int(os.getenv("CATALOG_HTTP_CACHE_SECONDS", "30"))
CATALOG_HTTP_CACHE_MAX_BYTES = int(
    os.getenv("CATALOG_HTTP_CACHE_MAX_BYTES", str(1_048_576)),
)

# ── Email (SMTP Яндекс 360 on prod; see docs/infra-reg-ru.md) ────────
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", default=True)
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", default=False)
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "webmaster@localhost")
LEAD_NOTIFY_EMAIL = os.getenv("LEAD_NOTIFY_EMAIL", "")

# Admin Email OTP (passwordless staff login). Spec: docs/security-baseline.md.
# Prod: ADMIN_EMAIL_OTP_ENABLED=true + ALLOWED_EMAILS (SMTP required).
# ALLOWED_EMAILS: comma list of addresses and/or domains (@hoocon.ru / *@hoocon.ru).
ADMIN_EMAIL_OTP_ENABLED = _env_bool("ADMIN_EMAIL_OTP_ENABLED", default=False)
ADMIN_EMAIL_OTP_TTL_SECONDS = int(os.getenv("ADMIN_EMAIL_OTP_TTL_SECONDS", "300"))
ADMIN_EMAIL_OTP_MAX_ATTEMPTS = int(os.getenv("ADMIN_EMAIL_OTP_MAX_ATTEMPTS", "5"))
ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("ADMIN_EMAIL_OTP_RESEND_COOLDOWN_SECONDS", "60"),
)
# Comma-separated; empty = any active staff (local/CI). Prod example: @hoocon.ru
ADMIN_EMAIL_OTP_ALLOWED_EMAILS = os.getenv("ADMIN_EMAIL_OTP_ALLOWED_EMAILS", "")
ADMIN_EMAIL_OTP_REQUEST_LIMIT = int(os.getenv("ADMIN_EMAIL_OTP_REQUEST_LIMIT", "5"))
ADMIN_EMAIL_OTP_REQUEST_WINDOW_SECONDS = int(
    os.getenv("ADMIN_EMAIL_OTP_REQUEST_WINDOW_SECONDS", "600"),
)

# ── Logging (PII-safe: never log full phone/email; see security-baseline §3.2) ─
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "hoocon": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
