from django.contrib import admin
from teachers.models import HomeroomAssignment
from teachers.models import Teacher
from teachers.models import TeacherQualification
from teachers.models import TeacherSubjectAssignment


class TeacherQualificationInline(admin.TabularInline):
    model = TeacherQualification
    extra = 1


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "get_user_name",
        "branch",
        "organization",
        "joining_date",
    )
    search_fields = ("employee_id", "specialization")
    list_filter = ("branch", "organization", "joining_date")
    inlines = [TeacherQualificationInline]

    @admin.display(description="Name")
    def get_user_name(self, obj):
        return obj.user.name


@admin.register(TeacherQualification)
class TeacherQualificationAdmin(admin.ModelAdmin):
    list_display = ("teacher", "degree_name", "institution", "completion_date")
    search_fields = ("teacher__employee_id", "degree_name")
    list_filter = ("degree_name", "organization")


@admin.register(TeacherSubjectAssignment)
class TeacherSubjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "subject", "section", "academic_year")
    search_fields = ("teacher__employee_id", "subject__name", "section__name")
    list_filter = ("academic_year", "organization", "teacher__branch")


@admin.register(HomeroomAssignment)
class HomeroomAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "get_section",
        "get_grade",
        "get_teacher_name",
        "get_teacher_id",
        "academic_year",
        "branch",
        "organization",
    )
    search_fields = (
        "teacher__employee_id",
        "section__name",
        "section__grade__name",
        "academic_year__name",
    )
    list_filter = ("academic_year", "organization", "branch")
    raw_id_fields = ("teacher", "section")

    @admin.display(description="Section")
    def get_section(self, obj):
        return obj.section.name

    @admin.display(description="Grade")
    def get_grade(self, obj):
        return obj.section.grade.name

    @admin.display(description="Teacher")
    def get_teacher_name(self, obj):
        return obj.teacher.user.name

    @admin.display(description="Employee ID")
    def get_teacher_id(self, obj):
        return obj.teacher.employee_id
