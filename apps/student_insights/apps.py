from importlib import import_module

from django.apps import AppConfig


class StudentInsightsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "student_insights"

    def ready(self):
        import_module("student_insights.signals")
