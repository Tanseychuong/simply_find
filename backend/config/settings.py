"""
Django settings for SimplyFind.

Env-driven throughout — same philosophy as the Flask config.py it replaces,
so dev/test/prod run off different env vars with no code changes.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DEBUG", "False") == "True"
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
if not DEBUG and SECRET_KEY in ("", "dev-secret-change-me", "change-me"):
    # Signing JWTs with a publicly known key would let anyone mint tokens.
    raise RuntimeError("SECRET_KEY must be set to a real secret when DEBUG=False")
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
# Render sets this to the service's public hostname (e.g. simplyfind-api.onrender.com).
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "config.apps.SimplyFindAdminConfig",   # django.contrib.admin with the SimplyFind dashboard (config/admin_site.py)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",   # signing out revokes the refresh token
    "corsheaders",
    "django_filters",

    # Local apps
    "apps.accounts",
    "apps.opportunities",
    "apps.ingestion",
    "apps.analytics",
    "apps.companies",
    "apps.documents",
    "apps.profiles",
    "apps.drives",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",              # must sit above CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if not DEBUG:
    # Serves admin CSS/JS under gunicorn; runserver already does this in dev.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],   # admin dashboard + branding overrides
        "APP_DIRS": True,   # Django admin's templates need this
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# DATABASE_URL parsed by hand (one less dependency than dj-database-url) —
# postgres://user:pass@host:port/dbname

def _parse_database_url(url: str) -> dict:
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        # Percent-decoded so passwords containing @ : / etc. can be
        # URL-encoded (e.g. @ -> %40) as hosts like Supabase expect.
        "USER": unquote(parsed.username) if parsed.username else None,
        "PASSWORD": unquote(parsed.password) if parsed.password else None,
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        # Connection pooling / resilience — mirrors the Flask
        # SQLALCHEMY_ENGINE_OPTIONS pool settings.
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", 300)),
        # Check reused connections are alive before using them, so a Supabase
        # restart or dropped pooler connection doesn't surface as errors.
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": 10},
    }


DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://localhost:5432/simplyfind")
DATABASES = {"default": _parse_database_url(DATABASE_URL)}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Django REST Framework + JWT
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Like simplejwt's JWTAuthentication, but an expired/invalid token is
        # treated as anonymous so public endpoints don't 401.
        "apps.accounts.authentication.OptionalJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    # Same as DRF's PageNumberPagination, plus ?page_size= (capped by MAX_PAGE_SIZE).
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": int(os.environ.get("DEFAULT_PAGE_SIZE", 20)),
    # Only views that set throttle_scope are throttled — login and register,
    # to slow down password guessing and sign-up spam, and the page-view
    # beacon, so one client can't flood the visitor stats.
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {
        "auth": os.environ.get("AUTH_THROTTLE_RATE", "10/min"),
        # Token refresh: a page opened in several tabs refreshes in each.
        "refresh": os.environ.get("REFRESH_THROTTLE_RATE", "60/min"),
        "analytics": os.environ.get("ANALYTICS_THROTTLE_RATE", "60/min"),
        # Company accounts and in-app applications (apps/companies/views.py).
        "company_signup": os.environ.get("COMPANY_SIGNUP_THROTTLE_RATE", "5/hour"),
        "company_jobs": os.environ.get("COMPANY_JOBS_THROTTLE_RATE", "30/hour"),
        "applications": os.environ.get("APPLICATIONS_THROTTLE_RATE", "20/hour"),
        "uploads": os.environ.get("UPLOADS_THROTTLE_RATE", "20/hour"),
        # Team invitations send email to addresses a company types in.
        "company_invites": os.environ.get("COMPANY_INVITES_THROTTLE_RATE", "20/hour"),
        # Applicant lists leaving the site as CSV or print.
        "exports": os.environ.get("EXPORTS_THROTTLE_RATE", "30/hour"),
        # Students signed up at a recruitment drive desk (one laptop, a queue of people).
        "desk_signups": os.environ.get("DESK_SIGNUPS_THROTTLE_RATE", "200/hour"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,   # a stolen, already-used refresh token is useless
    # Refuses refresh tokens issued before a password reset, or for
    # deactivated accounts (apps/accounts/authentication.py).
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.authentication.CurrentTokenRefreshSerializer",
}

# Sign-in cookies (apps/accounts/sessions.py). HttpOnly, so JavaScript never
# sees the tokens. SameSite=Lax suits an API on a subdomain of the site
# (api.simplyfind.app + simplyfind.app). If the API lives on another
# site entirely (e.g. *.onrender.com), set AUTH_COOKIE_SAMESITE=None.
AUTH_ACCESS_COOKIE = "sf_access"
AUTH_REFRESH_COOKIE = "sf_refresh"
AUTH_REFRESH_COOKIE_PATH = "/api/auth/"          # the refresh token is only sent to auth endpoints
AUTH_COOKIE_SECURE = not DEBUG
AUTH_COOKIE_SAMESITE = os.environ.get("AUTH_COOKIE_SAMESITE", "Lax")
AUTH_COOKIE_DOMAIN = os.environ.get("AUTH_COOKIE_DOMAIN", "")
CSRF_COOKIE_SAMESITE = AUTH_COOKIE_SAMESITE
CSRF_COOKIE_DOMAIN = AUTH_COOKIE_DOMAIN or None

# Applying and creating a company need a confirmed email; staff and company
# teams need two-step sign-in for applicant data and moderation. Both are
# only switched off by tests; there is deliberately no environment variable.
REQUIRE_VERIFIED_EMAIL = True
REQUIRE_MFA_FOR_STAFF_AND_COMPANIES = True
# Applying needs the first two profile steps and passes the student and
# recent-graduate rules (apps/profiles/eligibility.py).
REQUIRE_ELIGIBILITY_TO_APPLY = True

# "Sign in with Google": the OAuth client ID from Google Cloud Console
# (APIs & Services -> Credentials -> Web application). The frontend uses the
# same ID as VITE_GOOGLE_CLIENT_ID. Unset = Google sign-in is switched off.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()

MAX_PAGE_SIZE = int(os.environ.get("MAX_PAGE_SIZE", 100))


# ---------------------------------------------------------------------------
# Automatic ingestion (apps/ingestion — see docs/ingestion.md)
# ---------------------------------------------------------------------------
# Production: run `python manage.py run_ingestion_worker` as its own process.
# Development: with INGESTION_AUTOSTART on (the default while DEBUG=True),
# `runserver` starts the same worker in a background thread.

INGESTION_AUTOSTART = os.environ.get("INGESTION_AUTOSTART", str(DEBUG)) == "True"
INGESTION_WORKER_INTERVAL_SECONDS = int(os.environ.get("INGESTION_WORKER_INTERVAL_SECONDS", 60))
INGESTION_SOURCE_BATCH = int(os.environ.get("INGESTION_SOURCE_BATCH", 10))
INGESTION_ENRICH_BATCH = int(os.environ.get("INGESTION_ENRICH_BATCH", 25))
INGESTION_USER_AGENT = os.environ.get(
    "INGESTION_USER_AGENT", "SimplyFindBot/1.0"
)

# Public landing-page stats are cached briefly so the homepage doesn't run
# several COUNT queries on every visit.
LANDING_STATS_CACHE_SECONDS = int(os.environ.get("LANDING_STATS_CACHE_SECONDS", 120))


# ---------------------------------------------------------------------------
# Logging — the worker logs what it fetched/enriched; send it to stdout so
# the hosting platform's log viewer picks it up.
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "apps": {"handlers": ["console"], "level": os.environ.get("APP_LOG_LEVEL", "INFO"), "propagate": False},
    },
}


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# Canonical public site, used for sitemap.xml and email links (config/seo.py).
# Production must say where the site lives: email links depend on it.
SITE_URL = os.environ.get("SITE_URL", "" if not DEBUG else "http://localhost:5173").rstrip("/")
if not SITE_URL:
    raise RuntimeError("Set SITE_URL to the public site, e.g. https://simplyfind.example")
# Where reset-password links and the admin's "View site" link go.
FRONTEND_URL = os.environ.get("FRONTEND_URL", SITE_URL).rstrip("/")

# The site itself is always allowed. CORS_ALLOWED_ORIGINS (comma-separated)
# adds more, e.g. a www. alias or a preview deploy; local dev adds Vite.
_PRODUCTION_ORIGINS = list(dict.fromkeys([SITE_URL, FRONTEND_URL]))
_extra_origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
_dev_origins = ["http://localhost:5173", "http://127.0.0.1:5173"] if DEBUG else []
CORS_ALLOWED_ORIGINS = list(dict.fromkeys(_PRODUCTION_ORIGINS + _extra_origins + _dev_origins))

# Needed for logins, submissions and anything that POSTs
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS
CORS_ALLOW_CREDENTIALS = True   # the frontend sends the sign-in cookies

# Render deploy hook for the static site. When set, suspending a company or
# rejecting a live listing rebuilds the site at once, so its pre-rendered
# pages come down (config/seo.py: request_site_rebuild).
FRONTEND_DEPLOY_HOOK = os.environ.get("FRONTEND_DEPLOY_HOOK", "")

# How long applications are kept after their job closes, in days. Blank =
# keep until the applicant withdraws or deletes their account (the default
# until a retention period is decided). Enforced by
# `manage.py prune_applications`; keep the Privacy notice in sync.
APPLICATION_RETENTION_DAYS = int(os.environ["APPLICATION_RETENTION_DAYS"]) if os.environ.get("APPLICATION_RETENTION_DAYS") else None


# ---------------------------------------------------------------------------
# Email (password reset). Render's free plan blocks SMTP, so production sends
# through Brevo's HTTP API when BREVO_API_KEY is set; otherwise emails are
# printed to the console (handy in dev).
# ---------------------------------------------------------------------------

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
EMAIL_BACKEND = (
    "apps.accounts.email_backends.BrevoEmailBackend"
    if BREVO_API_KEY
    else "django.core.mail.backends.console.EmailBackend"
)
# Must be a sender address verified in Brevo.
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "SimplyFind <no-reply@localhost>")
# How long a password reset link stays valid (seconds).
PASSWORD_RESET_TIMEOUT = int(os.environ.get("PASSWORD_RESET_TIMEOUT", 3600))


# ---------------------------------------------------------------------------
# HTTPS hardening — on whenever DEBUG is off. Hosts like Render/Railway/Heroku
# terminate TLS at a proxy and pass the original scheme in X-Forwarded-Proto.
# ---------------------------------------------------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True") == "True"
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]   # platform health checks may probe over plain HTTP
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Off by default: once a browser sees HSTS it refuses plain HTTP for the
    # whole period. Set e.g. 31536000 after confirming HTTPS works end to end.
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 0))
    CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]


# ---------------------------------------------------------------------------
# I18N / static
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # filled by collectstatic, served by WhiteNoise
# SimplyFind eligibility: who counts as a student or recent graduate.
# A role may ask for at most MAX_EXPERIENCE_YEARS of experience, and
# graduates can apply for RECENT_GRADUATE_YEARS after their graduation year.
MAX_EXPERIENCE_YEARS = int(os.environ.get("MAX_EXPERIENCE_YEARS", 2))
RECENT_GRADUATE_YEARS = int(os.environ.get("RECENT_GRADUATE_YEARS", 2))

# Media (user uploads — currently just profile pictures). Production stores
# them in a public Supabase Storage bucket through its S3-compatible API;
# local dev keeps them on disk under MEDIA_ROOT (served by config/urls.py).
# Keys come from Supabase → Project Settings → Storage → S3 Connection.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")      # https://<ref>.supabase.co
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "")

if SUPABASE_URL and SUPABASE_STORAGE_BUCKET:
    _media_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": SUPABASE_STORAGE_BUCKET,
            "endpoint_url": f"{SUPABASE_URL}/storage/v1/s3",
            "region_name": os.environ.get("SUPABASE_S3_REGION", "us-east-1"),
            "access_key": os.environ.get("SUPABASE_S3_ACCESS_KEY_ID"),
            "secret_key": os.environ.get("SUPABASE_S3_SECRET_ACCESS_KEY"),
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,          # Supabase manages access per bucket, not per object
            "file_overwrite": False,      # a re-upload gets a new name, so stale CDN copies don't linger
            "querystring_auth": False,    # bucket is public — plain, non-expiring URLs
            # Public object URL: https://<ref>.supabase.co/storage/v1/object/public/<bucket>/<key>
            "custom_domain": f"{SUPABASE_URL.split('://', 1)[-1]}/storage/v1/object/public/{SUPABASE_STORAGE_BUCKET}",
        },
    }
elif not DEBUG:
    # Most hosts wipe local disk on deploy, and Django doesn't serve MEDIA
    # with DEBUG off — uploads would silently disappear.
    raise RuntimeError("Set SUPABASE_URL and SUPABASE_STORAGE_BUCKET (and S3 keys) when DEBUG=False")
else:
    _media_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

# Student documents and application files (CVs, transcripts...) are
# personal data: they go to a separate PRIVATE bucket, never the public
# one, and are only ever streamed through signed-in download endpoints.
# Production refuses to start without one. Local development keeps them on
# disk.
SUPABASE_PRIVATE_BUCKET = os.environ.get("SUPABASE_PRIVATE_BUCKET", "")
if SUPABASE_URL and SUPABASE_PRIVATE_BUCKET and "OPTIONS" in _media_storage:
    _private_options = {k: v for k, v in _media_storage["OPTIONS"].items() if k != "custom_domain"}
    _application_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {**_private_options, "bucket_name": SUPABASE_PRIVATE_BUCKET, "querystring_auth": True,
                    "querystring_expire": 300},
    }
elif not DEBUG:
    raise RuntimeError("Set SUPABASE_PRIVATE_BUCKET: students' documents must never go to the public bucket")
else:
    _application_storage = _media_storage

STORAGES = {
    "default": _media_storage,
    "applications": _application_storage,
    # The manifest backend needs collectstatic to have run, so dev/tests keep
    # Django's plain storage.
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
                    else "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 5))

# Virus scanning of every upload (apps/documents/uploads.py) through a
# ClamAV daemon. Required in production: with no reachable scanner,
# uploads are refused rather than stored unscanned. Set
# VIRUS_SCAN_REQUIRED=False only knowingly (e.g. a demo without ClamAV).
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", 3310))
CLAMAV_TIMEOUT = int(os.environ.get("CLAMAV_TIMEOUT", 15))
VIRUS_SCAN_REQUIRED = os.environ.get("VIRUS_SCAN_REQUIRED", str(not DEBUG)) == "True"
