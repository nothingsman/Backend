"""
With these settings, tests run faster.
"""

import base64
import hashlib

from .base import *  # noqa: F403
from .base import TEMPLATES
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="hbyGNr4PSfmMwygI0qGObzavF4C5eZ7fPh0dBLFJwRT65MdbxpdxuUfsEqEc0JK3",
)
PII_ENCRYPTION_ACTIVE_KEY = env(
    "PII_ENCRYPTION_ACTIVE_KEY",
    default=base64.urlsafe_b64encode(
        hashlib.sha256(f"{SECRET_KEY}:pii".encode()).digest(),
    ).decode("utf-8"),
)
PII_ENCRYPTION_KEYS = {
    **PII_ENCRYPTION_LEGACY_KEYS,  # noqa: F405
    PII_ENCRYPTION_ACTIVE_KEY_VERSION: PII_ENCRYPTION_ACTIVE_KEY,  # noqa: F405
}
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# DEBUGGING FOR TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore[index]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "http://media.testserver/"
# Your stuff...
# ------------------------------------------------------------------------------

# CELERY
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
