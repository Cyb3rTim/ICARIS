"""Settings for the automated test suite.

Runs with DEBUG off (production-like) and a fixed, non-secret key so tests
never depend on a developer's .env file.
"""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret-" + "x" * 40)
os.environ.setdefault("DJANGO_DEBUG", "false")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost")
os.environ.setdefault("DJANGO_SECURE_SSL_REDIRECT", "false")

from .settings import *  # noqa: E402,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast hashing in tests only

# Tests render templates without running collectstatic first.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MIDDLEWARE = [m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"]  # noqa: F405
