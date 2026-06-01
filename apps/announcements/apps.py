from importlib import import_module

from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "announcements"

    def ready(self):
        import_module("announcements.signals")
