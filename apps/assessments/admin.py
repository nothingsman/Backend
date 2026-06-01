from assessments.models import Assessment
from assessments.models import AssessmentResult
from assessments.models import HomeworkConfirmation
from django.contrib import admin


class AssessmentResultInline(admin.TabularInline):
    model = AssessmentResult
    extra = 0
    fields = (
        "student",
        "obtained_marks",
        "submission_status",
        "parent_confirmed",
        "feedback",
    )
    readonly_fields = ("parent_confirmed_by", "parent_confirmed_at")


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "task_type",
        "get_section",
        "get_subject",
        "get_teacher",
        "total_marks",
        "due_date",
        "status",
        "organization",
    )
    list_filter = ("task_type", "status", "organization", "branch")
    search_fields = (
        "title",
        "teacher_assignment__section__name",
        "teacher_assignment__subject__name",
    )
    inlines = [AssessmentResultInline]
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Section")
    def get_section(self, obj):
        return obj.teacher_assignment.section.name

    @admin.display(description="Subject")
    def get_subject(self, obj):
        return obj.teacher_assignment.subject.name

    @admin.display(description="Teacher")
    def get_teacher(self, obj):
        return obj.teacher_assignment.teacher.user.name


@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = (
        "get_student_name",
        "get_assessment_title",
        "obtained_marks",
        "get_total",
        "submission_status",
        "parent_confirmed",
        "graded_by",
    )
    list_filter = ("submission_status", "parent_confirmed", "organization")
    search_fields = ("student__roll_no", "assessment__title")
    readonly_fields = (
        "parent_confirmed_by",
        "parent_confirmed_at",
        "graded_by",
        "created_at",
        "updated_at",
    )

    @admin.display(description="Student")
    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    @admin.display(description="Assessment")
    def get_assessment_title(self, obj):
        return obj.assessment.title

    @admin.display(description="Total Marks")
    def get_total(self, obj):
        return obj.assessment.total_marks


@admin.register(HomeworkConfirmation)
class HomeworkConfirmationAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "assessment",
        "is_confirmed",
        "confirmed_by",
        "confirmed_at",
    )
    list_filter = ("is_confirmed", "organization", "branch", "section")
    search_fields = ("student__roll_no", "assessment__title")
    readonly_fields = ("created_at", "updated_at", "confirmed_at")
