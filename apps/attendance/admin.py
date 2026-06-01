from attendance.models import Attendance
from attendance.models import AttendanceReason
from attendance.models import AttendanceSummary
from django.contrib import admin


class AttendanceReasonInline(admin.StackedInline):
    model = AttendanceReason
    extra = 0
    fields = (
        "reason_category",
        "note",
        "parent_confirmed",
        "confirmed_by",
        "confirmed_at",
    )
    readonly_fields = ("confirmed_by", "confirmed_at")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "get_student_name",
        "date",
        "status",
        "section",
        "academic_year",
        "branch",
        "recorded_by",
    )
    list_filter = ("status", "date", "academic_year", "branch", "organization")
    search_fields = (
        "student__roll_no",
        "section__name",
    )
    inlines = [AttendanceReasonInline]
    date_hierarchy = "date"
    readonly_fields = ("client_side_id", "recorded_by", "created_at", "updated_at")

    @admin.display(description="Student")
    def get_student_name(self, obj):
        return (
            f"{obj.student.first_name} {obj.student.last_name} ({obj.student.roll_no})"
        )


@admin.register(AttendanceReason)
class AttendanceReasonAdmin(admin.ModelAdmin):
    list_display = (
        "get_student",
        "get_date",
        "reason_category",
        "parent_confirmed",
        "confirmed_by",
    )
    list_filter = ("reason_category", "parent_confirmed", "organization")
    search_fields = ("attendance__student__roll_no", "note")
    readonly_fields = ("confirmed_by", "confirmed_at", "created_at", "updated_at")

    @admin.display(description="Student")
    def get_student(self, obj):
        s = obj.attendance.student
        return f"{s.first_name} {s.last_name}"

    @admin.display(description="Date")
    def get_date(self, obj):
        return obj.attendance.date


@admin.register(AttendanceSummary)
class AttendanceSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "get_student_name",
        "academic_year",
        "total_present",
        "total_absent",
        "total_late",
        "total_excused",
        "total_school_days",
        "last_updated",
    )
    list_filter = ("academic_year", "organization")
    search_fields = ("student__roll_no",)
    readonly_fields = (
        "total_present",
        "total_absent",
        "total_late",
        "total_excused",
        "total_school_days",
        "last_updated",
    )

    @admin.display(description="Student")
    def get_student_name(self, obj):
        s = obj.student
        return f"{s.first_name} {s.last_name} ({s.roll_no})"
