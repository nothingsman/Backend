# ruff: noqa: PLR2004
from academics.models import AcademicYear
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceReason
from attendance.models import AttendanceSummary
from django.core.management import call_command
from organizations.models import Organization
from students.models import ParentStudentLink
from students.models import Student
from teachers.models import TeacherSubjectAssignment


def test_populate_one_month_data_command_creates_seeded_dataset(db):
    call_command(
        "populate_one_month_data",
        days=14,
        students_per_section=2,
        seed=7,
        owner_email="command-test-owner@example.com",
        organization_name="Command Test Demo Organization",
    )

    organization = Organization.objects.get(name="Command Test Demo Organization")
    academic_year = AcademicYear.objects.get(organization=organization, is_current=True)
    students = Student.objects.filter(organization=organization)

    assert organization.branches.count() == 1
    assert students.count() == 12
    assert (
        ParentStudentLink.objects.filter(student__organization=organization).count()
        == 12
    )
    assert (
        TeacherSubjectAssignment.objects.filter(organization=organization).count() == 24
    )
    assert Assessment.objects.filter(organization=organization).count() == 72
    assert AssessmentResult.objects.filter(organization=organization).count() == 144
    assert Attendance.objects.filter(organization=organization).exists()
    assert AttendanceReason.objects.filter(organization=organization).exists()
    assert (
        AttendanceSummary.objects.filter(
            organization=organization,
            academic_year=academic_year,
        ).count()
        == students.count()
    )
