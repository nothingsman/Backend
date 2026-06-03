# ruff: noqa: ERA001, E501
"""Base settings to build other settings files upon."""

import json
import ssl
import sys
from pathlib import Path

import environ
from django.utils import timezone

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
sys.path.append(str(BASE_DIR / "apps"))
# core/
APPS_DIR = BASE_DIR / "core"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE = "UTC"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('fr-fr', _('French')),
#     ('pt-br', _('Portuguese')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.humanize", # Handy template tags
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "channels",
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.socialaccount",
    "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",
    "djoser",
    "django_filters",
]

LOCAL_APPS = [
    "accounts",
    "organizations",
    "schools",
    "branches",
    "academics",
    "students",
    "teachers",
    "attendance",
    "analytics",
    "assessments",
    "announcements",
    "core",
    "media",
    "messaging",
    "notifications",
    # Your stuff: custom apps go here
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

ASGI_APPLICATION = "config.asgi.application"

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES = {"sites": "core.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL = "accounts.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.allauth_settings",
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT = 5
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="noreply@example.com",
)
# Frontend URL for generating activation/password reset links in emails
# Used by Djoser email classes to generate ACTIVATION_URL and PASSWORD_RESET_CONFIRM_URL
# Format: https://yourdomain.com (no trailing slash)
FRONTEND_DOMAIN = env(
    "FRONTEND_DOMAIN",
    default="http://localhost:3000",
)
# Whether to use HTTPS in email links (useful for localhost:8000 but remote is https)
FRONTEND_PROTOCOL = env(
    "FRONTEND_PROTOCOL",
    default="http" if DEBUG else "https",
)
# Optional role-specific frontend domains used for activation/invitation links.
# Each value may be a full origin (for example https://teachers.kelem.app) or
# just a host (for example teachers.kelem.app). Unset roles fall back to
# FRONTEND_DOMAIN.
FRONTEND_ORGANIZATION_DOMAIN = env(
    "FRONTEND_ORGANIZATION_DOMAIN",
    default=FRONTEND_DOMAIN,
)
FRONTEND_BRANCH_ADMIN_DOMAIN = env(
    "FRONTEND_BRANCH_ADMIN_DOMAIN",
    default=FRONTEND_DOMAIN,
)
FRONTEND_TEACHER_DOMAIN = env(
    "FRONTEND_TEACHER_DOMAIN",
    default=FRONTEND_DOMAIN,
)
FRONTEND_PARENT_DOMAIN = env(
    "FRONTEND_PARENT_DOMAIN",
    default=FRONTEND_DOMAIN,
)
FRONTEND_ROLE_DOMAINS = {
    "ORGANIZATION": FRONTEND_ORGANIZATION_DOMAIN,
    "BRANCH_ADMIN": FRONTEND_BRANCH_ADMIN_DOMAIN,
    "TEACHER": FRONTEND_TEACHER_DOMAIN,
    "PARENT": FRONTEND_PARENT_DOMAIN,
}

# PII field encryption
# ------------------------------------------------------------------------------
PII_ENCRYPTION_ACTIVE_KEY_VERSION = env(
    "PII_ENCRYPTION_ACTIVE_KEY_VERSION",
    default="v1",
)
PII_ENCRYPTION_ACTIVE_KEY = env(
    "PII_ENCRYPTION_ACTIVE_KEY",
    default="",
)
PII_ENCRYPTION_LEGACY_KEYS = json.loads(
    env(
        "PII_ENCRYPTION_LEGACY_KEYS",
        default="{}",
    ),
)
PII_ENCRYPTION_KEYS = {
    **PII_ENCRYPTION_LEGACY_KEYS,
    PII_ENCRYPTION_ACTIVE_KEY_VERSION: PII_ENCRYPTION_ACTIVE_KEY,
}
SMS_BACKEND = env(
    "SMS_BACKEND",
    default="accounts.sms.LoggingSMSBackend",
)
TELERIVET_API_KEY = env("TELERIVET_API_KEY", default="")
TELERIVET_PROJECT_ID = env("TELERIVET_PROJECT_ID", default="")
TELERIVET_TIMEOUT_SECONDS = env.int("TELERIVET_TIMEOUT_SECONDS", default=10)
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
GEMINI_INSIGHT_MODEL = env("GEMINI_INSIGHT_MODEL", default="gemini-2.5-flash")
PARENT_OTP_EXPIRY_SECONDS = env.int(
    "PARENT_OTP_EXPIRY_SECONDS",
    default=300,
)
PARENT_OTP_MAX_ATTEMPTS = env.int(
    "PARENT_OTP_MAX_ATTEMPTS",
    default=5,
)
# ETHIOPIA ETRADE VERIFICATION
# ------------------------------------------------------------------------------
ETRADE_API_BASE_URL = env(
    "ETRADE_API_BASE_URL",
    default="https://etrade.gov.et/api",
)
ETRADE_API_TIMEOUT = env.int("ETRADE_API_TIMEOUT", default=10)
ETRADE_API_REFERER = env(
    "ETRADE_API_REFERER",
    default="https://etrade.gov.et/",
)
ETRADE_API_USER_AGENT = env(
    "ETRADE_API_USER_AGENT",
    default="Mozilla/5.0",
)

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = ['"oddegen" <oddegen@api.kelem.app>']
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")
REDIS_SSL = REDIS_URL.startswith("rediss://")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Celery
# ------------------------------------------------------------------------------
if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE = TIME_ZONE
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_NONE} if REDIS_SSL else None
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND = REDIS_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#redis-backend-use-ssl
CELERY_REDIS_BACKEND_USE_SSL = CELERY_BROKER_USE_SSL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT = ["json"]
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_TIME_LIMIT = 5 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
# TODO: set to whatever value is adequate in your circumstances
CELERY_TASK_SOFT_TIME_LIMIT = 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#beat-scheduler
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
# Periodic tasks
# Run academic year rollover every year on September 1st at 00:05 UTC
# (Ethiopian new academic year starts September 1)
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "rollover-academic-years-annually": {
        "task": "academics.tasks.rollover_academic_years",
        "schedule": crontab(minute=5, hour=0, day_of_month=1, month_of_year=9),
    },
}
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-hijack-root-logger
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# django-allauth
# ------------------------------------------------------------------------------
ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_LOGIN_METHODS = {"email"}
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
# https://docs.allauth.org/en/latest/account/forms.html
ACCOUNT_FORMS = {"signup": "accounts.forms.UserSignupForm"}
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_FORMS = {"signup": "accounts.forms.UserSocialSignupForm"}

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("DRF_THROTTLE_ANON_RATE", default="30/minute"),
        "user": env("DRF_THROTTLE_USER_RATE", default="120/minute"),
    },
    "PAGE_SIZE": 10,
    "EXCEPTION_HANDLER": "core.api.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer", "JWT"),
    "USER_AUTHENTICATION_RULE": "accounts.auth.user_authentication_rule",
}


# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
# Origins must be full scheme+host(+port), not URL paths.
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^/api/.*$",
    r"^/auth/.*$",
    r"^https://([a-z0-9-]+\.)?kelem\.app$",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
)

# JWT refresh cookie settings (cross-origin compatible defaults for local dev)
JWT_REFRESH_COOKIE_NAME = env("JWT_REFRESH_COOKIE_NAME", default="refresh_token")
JWT_REFRESH_COOKIE_PATH = env("JWT_REFRESH_COOKIE_PATH", default="/auth/jwt/")
JWT_REFRESH_COOKIE_DOMAIN = env("JWT_REFRESH_COOKIE_DOMAIN", default=None)
JWT_REFRESH_COOKIE_SECURE = env.bool("JWT_REFRESH_COOKIE_SECURE", default=False)
JWT_REFRESH_COOKIE_HTTPONLY = env.bool("JWT_REFRESH_COOKIE_HTTPONLY", default=True)
JWT_REFRESH_COOKIE_SAMESITE = env(
    "JWT_REFRESH_COOKIE_SAMESITE",
    default="Lax",
)
# By Default swagger ui is available only to admin user(s). You can change permission classes to change that
# See more configuration options at https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS = {
    "TITLE": "core API",
    "DESCRIPTION": "Documentation of API endpoints of core",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SCHEMA_PATH_PREFIX": "/api/",
}

# Media Upload Settings
# -----------------------------------------------------------------------
MEDIA_UPLOAD_SETTINGS = {
    "BUCKET_NAME": env("S3_BUCKET", default=""),
    "REGION": env("S3_REGION", default=""),
    "ENDPOINT_URL": env("S3_PUBLIC_ENDPOINT", default="")
    or env("S3_ENDPOINT", default=""),
    "INTERNAL_ENDPOINT_URL": env("S3_INTERNAL_ENDPOINT", default=""),
    "PRESIGNED_URL_TTL": env.int("S3_PRESIGNED_URL_TTL", default=900),
    "DOWNLOAD_URL_TTL": env.int("S3_DOWNLOAD_URL_TTL", default=86400),
    "UPLOAD_TTL": env.int("S3_UPLOAD_TTL", default=3600),
    "FINGERPRINT_WINDOW": env.int("S3_FINGERPRINT_WINDOW", default=3600),
    "FILE_SIZE_LIMITS": {
        "image/*": env.int("MEDIA_MAX_IMAGE_SIZE", default=10_000_000),
        "video/*": env.int("MEDIA_MAX_VIDEO_SIZE", default=500_000_000),
        "application/pdf": env.int("MEDIA_MAX_PDF_SIZE", default=50_000_000),
        "default": env.int("MEDIA_MAX_DEFAULT_SIZE", default=100_000_000),
    },
}

S3_ACCESS_KEY_ID = env("S3_ACCESS_KEY_ID", default="")
S3_SECRET_ACCESS_KEY = env("S3_SECRET_ACCESS_KEY", default="")

# Your stuff...
# ------------------------------------------------------------------------------

# Monkeypatch django-seed for Django 5.0+ compatibility
# django-seed uses is_dst which was removed in Django 5.0

original_make_aware = timezone.make_aware


def patched_make_aware(value, timezone_obj=None, is_dst=None):
    # Ignore is_dst if provided
    return original_make_aware(value, timezone_obj)


timezone.make_aware = patched_make_aware

DJOSER = {
    "TOKEN_MODEL": None,
    "EMAIL_FRONTEND_DOMAIN": FRONTEND_DOMAIN,
    "EMAIL_FRONTEND_PROTOCOL": FRONTEND_PROTOCOL,
    "SERIALIZERS": {
        "user_create": "accounts.api.serializers.UserCreateSerializer",
    },
    "SEND_ACTIVATION_EMAIL": True,
    "SEND_CONFIRMATION_EMAIL": True,
    "PASSWORD_CHANGED_EMAIL_CONFIRMATION": True,
    "EMAIL": {
        "activation": "accounts.email.ActivationEmail",
        "confirmation": "accounts.email.ConfirmationEmail",
        "password_reset": "accounts.email.PasswordResetEmail",
        "password_changed_confirmation": "accounts.email.PasswordChangedConfirmationEmail",
    },
    "ACTIVATION_URL": "activate/{uid}/{token}",
    "PASSWORD_RESET_CONFIRM_URL": "reset-password/{uid}/{token}",
}
