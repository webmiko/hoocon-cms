"""Django settings for Hoocon CMS."""

from __future__ import annotations

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

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

INSTALLED_APPS = [
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
    "redirects",
    "sitesettings",
    "catalog",
    "content",
    "leads",
    "crm.apps.CrmConfig",
    "search",
    "social",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
    "config.csp_middleware.CspMiddleware",
]

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

# ── SEO / SPA shell (БЗ SEO-индексация-SPA.md) ───────────────────────
SITE_URL = os.getenv("SITE_URL", "https://hoocon.ru").rstrip("/")
_SPA_DEFAULT = str(BASE_DIR.parent / "frontend" / "dist" / "index.html")
SPA_INDEX_HTML = os.getenv("SPA_INDEX_HTML", _SPA_DEFAULT)

# Analytics (fallback if SiteSettings IDs empty; SPA prefers /api/settings/public/).
YANDEX_METRIKA_ID = os.getenv("YANDEX_METRIKA_ID", "").strip()
GA4_MEASUREMENT_ID = os.getenv("GA4_MEASUREMENT_ID", "").strip()

# Social bots (secrets — never expose via API; chat IDs live in SiteSettings Admin).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
VK_ACCESS_TOKEN = os.getenv("VK_ACCESS_TOKEN", "").strip()
MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "").strip()

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
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Hoocon CMS API",
    "DESCRIPTION": "B2B catalog and content API for Hoocon HVAC actuators.",
    "VERSION": "0.1.0",
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", default=False)

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

# ── Email (SMTP reg.ru on prod; see docs/infra-reg-ru.md) ───────────
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = _env_bool("EMAIL_USE_SSL", default=True)
EMAIL_USE_TLS = _env_bool("EMAIL_USE_TLS", default=False)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "webmaster@localhost")
LEAD_NOTIFY_EMAIL = os.getenv("LEAD_NOTIFY_EMAIL", "")

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
