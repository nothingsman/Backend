import importlib
import sys


def test_production_settings_keep_staticfiles_local(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://postgres:postgres@db:5432/core")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("PII_ENCRYPTION_ACTIVE_KEY", "test-pii-key")
    monkeypatch.setenv("RESEND_API_KEY", "test-resend-key")
    monkeypatch.setenv("DJANGO_ADMIN_URL", "admin/")
    monkeypatch.setenv("DJANGO_AWS_STORAGE_BUCKET_NAME", "test-bucket")

    sys.modules.pop("config.settings.production", None)
    production_settings = importlib.import_module("config.settings.production")

    assert production_settings.STORAGES["staticfiles"]["BACKEND"] == (
        "whitenoise.storage.CompressedStaticFilesStorage"
    )
    assert production_settings.STATIC_URL == "/static/"
    assert "collectfasta" not in production_settings.INSTALLED_APPS

    sys.modules.pop("config.settings.production", None)
