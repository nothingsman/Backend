from analytics.models import InterventionLog
from django.contrib import admin


@admin.register(InterventionLog)
class InterventionLogAdmin(admin.ModelAdmin):
    list_display = (
        "get_student_name",
        "intervention_type",
        "severity",
        "status",
        "title",
        "source_model",
        "created_at",
    )
    list_filter = ("intervention_type", "severity", "status", "organization")
    search_fields = ("title", "description")
    readonly_fields = ("source_model", "source_id", "created_at", "updated_at")

    @admin.display(description="Student")
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
