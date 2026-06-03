from datetime import date

import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from attendance.models import Attendance
from attendance.models import AttendanceReason
from attendance.tests.factories import AttendanceFactory
from attendance.tests.factories import AttendanceReasonFactory
from attendance.tests.factories import AttendanceSummaryFactory
from branches.models import BranchAdmin
from branches.tests.factories import BranchFactory
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import HomeroomAssignment
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment


@pytest.mark.django_db
class TestAttendanceTeacherAccessAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture
    def branch(self, organization):
        return BranchFactory(school__organization=organization)

    @pytest.fixture
    def academic_year(self, organization, branch):
        return AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )

    @pytest.fixture
    def grade(self, organization, branch):
        return GradeFactory(organization=organization, branch=branch, level=7)

    @pytest.fixture
    def section(self, organization, branch, grade, academic_year):
        return SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="A",
        )

    @pytest.fixture
    def other_section(self, organization, branch, grade, academic_year):
        return SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="B",
        )

    @pytest.fixture
    def subject(self, organization, branch, grade):
        return SubjectFactory(organization=organization, branch=branch, grade=grade)

    @pytest.fixture
    def homeroom_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Homeroom Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-HR-1",
            specialization="General",
        )

    @pytest.fixture
    def assigned_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Assigned Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-AT-1",
            specialization="Math",
        )

    @pytest.fixture
    def unrelated_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Other Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-OT-1",
            specialization="Science",
        )

    @pytest.fixture
    def student(self, organization, branch, section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

    @pytest.fixture
    def other_student(self, organization, branch, other_section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )

    @pytest.fixture
    def attendance_record(self, organization, branch, academic_year, section, student):
        return AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            student=student,
            date=date(2026, 1, 15),
            status=Attendance.Status.PRESENT,
        )

    @pytest.fixture(autouse=True)
    def setup_assignments(  # noqa: PLR0913
        self,
        organization,
        branch,
        academic_year,
        section,
        other_section,
        subject,
        homeroom_teacher,
        assigned_teacher,
        unrelated_teacher,
    ):
        TeacherSubjectAssignment.objects.create(
            teacher=homeroom_teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=assigned_teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        TeacherSubjectAssignment.objects.create(
            teacher=unrelated_teacher,
            organization=organization,
            subject=subject,
            section=other_section,
            academic_year=academic_year,
        )
        HomeroomAssignment.objects.create(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            teacher=homeroom_teacher,
        )

    def test_assigned_teacher_can_list_attendance_for_own_section(
        self,
        api_client,
        assigned_teacher,
        attendance_record,
        section,
    ):
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.get("/api/attendance/", {"section": str(section.id)})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(attendance_record.id)

    def test_teacher_cannot_list_attendance_for_unassigned_section(
        self,
        api_client,
        assigned_teacher,
        other_section,
    ):
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.get(
            "/api/attendance/",
            {"section": str(other_section.id)},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_assigned_non_homeroom_teacher_cannot_create_attendance(  # noqa: PLR0913
        self,
        api_client,
        assigned_teacher,
        organization,
        branch,
        academic_year,
        section,
        student,
    ):
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.post(
            "/api/attendance/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "academic_year": str(academic_year.id),
                "section": str(section.id),
                "student": str(student.id),
                "date": "2026-01-16",
                "status": Attendance.Status.PRESENT,
                "remarks": "",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_homeroom_teacher_can_create_attendance(  # noqa: PLR0913
        self,
        api_client,
        homeroom_teacher,
        organization,
        branch,
        academic_year,
        section,
        student,
    ):
        api_client.force_authenticate(user=homeroom_teacher.user)

        response = api_client.post(
            "/api/attendance/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "academic_year": str(academic_year.id),
                "section": str(section.id),
                "student": str(student.id),
                "date": "2026-01-16",
                "status": Attendance.Status.LATE,
                "remarks": "Traffic",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["recorded_by"] == homeroom_teacher.user.id

    def test_assigned_non_homeroom_teacher_cannot_bulk_submit_attendance(  # noqa: PLR0913
        self,
        api_client,
        assigned_teacher,
        organization,
        branch,
        academic_year,
        section,
        student,
    ):
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.post(
            "/api/attendance/bulk-submit/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "academic_year": str(academic_year.id),
                "section": str(section.id),
                "date": "2026-01-17",
                "records": [
                    {
                        "student": str(student.id),
                        "status": Attendance.Status.PRESENT,
                    },
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_homeroom_teacher_can_bulk_submit_attendance(  # noqa: PLR0913
        self,
        api_client,
        homeroom_teacher,
        organization,
        branch,
        academic_year,
        section,
        student,
    ):
        api_client.force_authenticate(user=homeroom_teacher.user)

        response = api_client.post(
            "/api/attendance/bulk-submit/",
            {
                "organization": str(organization.id),
                "branch": str(branch.id),
                "academic_year": str(academic_year.id),
                "section": str(section.id),
                "date": "2026-01-17",
                "records": [
                    {
                        "student": str(student.id),
                        "status": Attendance.Status.PRESENT,
                    },
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] == 1

    def test_assigned_teacher_can_list_attendance_summaries_for_own_section(
        self,
        api_client,
        assigned_teacher,
        organization,
        student,
        academic_year,
    ):
        summary = AttendanceSummaryFactory(
            organization=organization,
            student=student,
            academic_year=academic_year,
            total_present=5,
            total_school_days=6,
        )
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.get("/api/attendance-summaries/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(summary.id)

    def test_teacher_cannot_list_attendance_summaries_for_unassigned_section(
        self,
        api_client,
        assigned_teacher,
        organization,
        other_student,
        academic_year,
    ):
        AttendanceSummaryFactory(
            organization=organization,
            student=other_student,
            academic_year=academic_year,
            total_present=2,
            total_school_days=4,
        )
        api_client.force_authenticate(user=assigned_teacher.user)

        response = api_client.get("/api/attendance-summaries/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_branch_admin_can_list_attendance_summaries(
        self,
        api_client,
        branch,
        organization,
        student,
        academic_year,
    ):
        summary = AttendanceSummaryFactory(
            organization=organization,
            student=student,
            academic_year=academic_year,
            total_present=7,
            total_school_days=8,
        )
        branch_admin_user = UserFactory(role="ADMIN", name="Branch Admin")
        BranchAdmin.objects.create(
            organization=organization,
            user=branch_admin_user,
            branch=branch,
            status=BranchAdmin.Status.ACTIVE,
        )
        api_client.force_authenticate(user=branch_admin_user)

        response = api_client.get("/api/attendance-summaries/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(summary.id)

    def test_assigned_non_homeroom_teacher_cannot_update_or_delete_attendance(
        self,
        api_client,
        assigned_teacher,
        attendance_record,
    ):
        api_client.force_authenticate(user=assigned_teacher.user)

        patch_response = api_client.patch(
            f"/api/attendance/{attendance_record.id}/",
            {"remarks": "Updated"},
            format="json",
        )
        delete_response = api_client.delete(f"/api/attendance/{attendance_record.id}/")

        assert patch_response.status_code == status.HTTP_403_FORBIDDEN
        assert delete_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAttendanceReasonParentAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def organization(self):
        return OrganizationFactory()

    @pytest.fixture
    def branch(self, organization):
        return BranchFactory(school__organization=organization)

    @pytest.fixture
    def academic_year(self, organization, branch):
        return AcademicYear.objects.get(
            organization=organization,
            branch=branch,
            name="2025/2026",
        )

    @pytest.fixture
    def grade(self, organization, branch):
        return GradeFactory(organization=organization, branch=branch, level=7)

    @pytest.fixture
    def section(self, organization, branch, grade, academic_year):
        return SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="A",
        )

    @pytest.fixture
    def student(self, organization, branch, section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

    @pytest.fixture
    def parent(self, organization, branch, student):
        parent = ParentFactory(
            organizations=[organization],
            branches=[branch],
        )
        ParentStudentLinkFactory(
            parent=parent,
            student=student,
            relationship_type="FATHER",
        )
        return parent

    @pytest.fixture
    def attendance_record(self, organization, branch, academic_year, section, student):
        return AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            student=student,
            date=date(2026, 5, 30),
            status=Attendance.Status.ABSENT,
        )

    @pytest.fixture
    def present_attendance_reason(
        self,
        organization,
        branch,
        academic_year,
        section,
        student,
    ):
        attendance_record = AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            student=student,
            date=date(2026, 5, 30),
            status=Attendance.Status.PRESENT,
        )
        return AttendanceReasonFactory(
            organization=organization,
            attendance=attendance_record,
        )

    def test_parent_can_create_reason_for_linked_student(
        self,
        api_client,
        parent,
        attendance_record,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.post(
            "/api/attendance-reasons/parent-create/",
            {
                "attendance": str(attendance_record.id),
                "reason_category": "SICKNESS",
                "note": "Had a fever",
                "parent_confirmed": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert AttendanceReason.objects.count() == 1
        reason = AttendanceReason.objects.get()
        assert reason.attendance_id == attendance_record.id
        assert reason.reason_category == "SICKNESS"
        assert reason.note == "Had a fever"
        assert reason.parent_confirmed is True

    def test_parent_create_upserts_existing_reason(
        self,
        api_client,
        parent,
        attendance_record,
        organization,
    ):
        AttendanceReasonFactory(
            organization=organization,
            attendance=attendance_record,
            reason_category=AttendanceReason.Category.UNKNOWN,
            note="Old note",
            parent_confirmed=False,
        )
        api_client.force_authenticate(user=parent.user)

        response = api_client.post(
            "/api/attendance-reasons/parent-create/",
            {
                "attendance": str(attendance_record.id),
                "reason_category": "EMERGENCY",
                "note": "Updated note",
                "parent_confirmed": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert AttendanceReason.objects.count() == 1
        reason = AttendanceReason.objects.get()
        assert reason.reason_category == "EMERGENCY"
        assert reason.note == "Updated note"
        assert reason.parent_confirmed is True

    def test_parent_cannot_create_reason_for_unlinked_student(
        self,
        api_client,
        attendance_record,
    ):
        api_client.force_authenticate(user=ParentFactory().user)

        response = api_client.post(
            "/api/attendance-reasons/parent-create/",
            {
                "attendance": str(attendance_record.id),
                "reason_category": "SICKNESS",
                "note": "Should fail",
                "parent_confirmed": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_parent_can_update_reason_for_linked_student(
        self,
        api_client,
        parent,
        attendance_record,
        organization,
    ):
        reason = AttendanceReasonFactory(
            organization=organization,
            attendance=attendance_record,
            reason_category=AttendanceReason.Category.UNKNOWN,
            note="Old note",
            parent_confirmed=False,
        )
        api_client.force_authenticate(user=parent.user)

        response = api_client.patch(
            f"/api/attendance-reasons/{reason.id}/parent-update/",
            {
                "reason_category": "SICKNESS",
                "note": "Had a fever",
                "parent_confirmed": True,
            },
            format="json",
        )

        reason.refresh_from_db()
        assert response.status_code == status.HTTP_200_OK
        assert reason.reason_category == "SICKNESS"
        assert reason.note == "Had a fever"
        assert reason.parent_confirmed is True
        assert reason.confirmed_by == parent.user

    def test_parent_cannot_update_reason_for_unlinked_student(
        self,
        api_client,
        attendance_record,
        organization,
    ):
        reason = AttendanceReasonFactory(
            organization=organization,
            attendance=attendance_record,
        )
        api_client.force_authenticate(user=ParentFactory().user)

        response = api_client.patch(
            f"/api/attendance-reasons/{reason.id}/parent-update/",
            {"note": "Should fail"},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_parent_update_returns_bad_request_when_reason_not_required(
        self,
        api_client,
        parent,
        present_attendance_reason,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.patch(
            f"/api/attendance-reasons/{present_attendance_reason.id}/parent-update/",
            {"note": "Should not be accepted"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
