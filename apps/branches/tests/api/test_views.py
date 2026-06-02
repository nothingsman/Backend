from __future__ import annotations

from decimal import Decimal

import pytest
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.tests.factories import AttendanceFactory
from attendance.tests.factories import AttendanceSummaryFactory
from branches.api.views import BranchAdminViewSet
from branches.api.views import BranchViewSet
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APIRequestFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment

from media.tests.factories import MediaFileFactory


@pytest.mark.django_db
class TestBranchViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    @pytest.fixture
    def api_client(self) -> APIClient:
        return APIClient()

    def test_get_queryset_scopes_to_request_owner(self, api_rf: APIRequestFactory):
        user = UserFactory()
        owned_branch = BranchFactory(school__organization__owner=user)
        foreign_branch = BranchFactory()
        view = BranchViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert list(queryset) == [owned_branch]
        assert foreign_branch not in queryset

    def test_get_queryset_includes_branch_admin_branch(
        self,
        api_rf: APIRequestFactory,
    ):
        user = UserFactory()
        branch = BranchFactory()
        BranchAdminFactory(user=user, branch=branch)
        foreign_branch = BranchFactory()
        view = BranchViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert list(queryset) == [branch]
        assert foreign_branch not in queryset

    def test_school_name_endpoint_returns_branch_school_name(
        self,
        api_client: APIClient,
    ):
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=user)
        api_client.force_authenticate(user=user)

        response = api_client.get(f"/api/branches/{branch.id}/school-name/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "branch_id": str(branch.id),
            "branch_name": branch.name,
            "logo": None,
            "school_id": str(branch.school_id),
            "school_name": branch.school.name,
        }

    def test_school_name_endpoint_allows_teacher_branch_access(
        self,
        api_client: APIClient,
    ):
        user = UserFactory()
        branch = BranchFactory(school__organization__owner=UserFactory())
        logo = MediaFileFactory(uploaded_by=user)
        branch.school.logo = logo
        branch.school.save(update_fields=["logo"])
        Teacher.objects.create(
            user=user,
            organization=branch.organization,
            branch=branch,
            employee_id="EMP-1000",
        )
        api_client.force_authenticate(user=user)

        response = api_client.get(f"/api/branches/{branch.id}/school-name/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "branch_id": str(branch.id),
            "branch_name": branch.name,
            "logo": str(logo.id),
            "school_id": str(branch.school_id),
            "school_name": branch.school.name,
        }

    def test_analytics_endpoint_returns_active_totals_and_performance_series(  # noqa: PLR0915
        self,
        api_client: APIClient,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        organization = branch.organization
        academic_year = branch.academic_years.get(name="2025/2026")
        api_client.force_authenticate(user=owner)

        grade = GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 8",
            level=8,
        )
        second_grade = GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 9",
            level=9,
        )
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="A",
        )
        second_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=second_grade,
            academic_year=academic_year,
            name="B",
        )

        active_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            status="ACTIVE",
        )
        second_active_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=second_section,
            status="ACTIVE",
        )
        StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            status="INACTIVE",
        )
        ParentStudentLinkFactory(student=active_student)

        AttendanceSummaryFactory(
            organization=organization,
            student=active_student,
            academic_year=academic_year,
            total_present=16,
            total_absent=2,
            total_excused=2,
            total_school_days=20,
        )
        AttendanceSummaryFactory(
            organization=organization,
            student=second_active_student,
            academic_year=academic_year,
            total_present=7,
            total_absent=2,
            total_excused=1,
            total_school_days=10,
        )

        AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            student=active_student,
            date=timezone.datetime(2025, 1, 6).date(),
            status=Attendance.Status.PRESENT,
        )
        AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            student=active_student,
            date=timezone.datetime(2025, 1, 7).date(),
            status=Attendance.Status.ABSENT,
        )
        AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=second_section,
            student=second_active_student,
            date=timezone.datetime(2025, 2, 3).date(),
            status=Attendance.Status.EXCUSED,
        )
        AttendanceFactory(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=second_section,
            student=second_active_student,
            date=timezone.datetime(2025, 2, 4).date(),
            status=Attendance.Status.LATE,
        )

        active_teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", is_active=True),
            organization=organization,
            branch=branch,
            employee_id="EMP-2001",
        )
        Teacher.objects.create(
            user=UserFactory(role="TEACHER", is_active=False),
            organization=organization,
            branch=branch,
            employee_id="EMP-2002",
        )

        BranchAdminFactory(
            organization=organization,
            branch=branch,
            user=UserFactory(role="BRANCH_ADMIN", is_active=True),
            status="ACTIVE",
        )
        BranchAdminFactory(
            organization=organization,
            branch=branch,
            user=UserFactory(role="BRANCH_ADMIN", is_active=False),
            status="ACTIVE",
        )
        BranchAdminFactory(
            organization=organization,
            branch=branch,
            user=UserFactory(role="BRANCH_ADMIN", is_active=True),
            status="INACTIVE",
        )

        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Mathematics",
            code="MATH-8",
        )
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=active_teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        second_subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=second_grade,
            name="English",
            code="ENG-9",
        )
        second_assignment = TeacherSubjectAssignment.objects.create(
            teacher=active_teacher,
            organization=organization,
            subject=second_subject,
            section=second_section,
            academic_year=academic_year,
        )

        assessment_q1 = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Quarter 1 Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("50.00"),
            due_date=timezone.datetime(2025, 1, 15).date(),
            status=Assessment.Status.PUBLISHED,
        )
        assessment_q2 = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Quarter 2 Exam",
            task_type=Assessment.TaskType.EXAM,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("50.00"),
            due_date=timezone.datetime(2025, 5, 15).date(),
            status=Assessment.Status.PUBLISHED,
        )
        assessment_grade9 = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=second_assignment,
            title="Grade 9 Midterm",
            task_type=Assessment.TaskType.EXAM,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("50.00"),
            due_date=timezone.datetime(2025, 5, 20).date(),
            status=Assessment.Status.PUBLISHED,
        )
        assessment_2026 = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Quarter 1 Final",
            task_type=Assessment.TaskType.EXAM,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("50.00"),
            due_date=timezone.datetime(2026, 2, 15).date(),
            status=Assessment.Status.PUBLISHED,
        )

        q1_result = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment_q1,
            student=active_student,
            obtained_marks=Decimal("80.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        q1_result.created_at = timezone.make_aware(timezone.datetime(2025, 2, 10, 9, 0))
        q1_result.save(update_fields=["created_at"])

        q2_result = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment_grade9,
            student=second_active_student,
            obtained_marks=Decimal("60.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        q2_result.created_at = timezone.make_aware(timezone.datetime(2025, 5, 12, 9, 0))
        q2_result.save(update_fields=["created_at"])

        result_2026 = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment_2026,
            student=active_student,
            obtained_marks=Decimal("90.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        result_2026.created_at = timezone.make_aware(
            timezone.datetime(2026, 1, 20, 9, 0),
        )
        result_2026.save(update_fields=["created_at"])

        ungraded_result = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment_q2,
            student=StudentFactory(
                organization=organization,
                branch=branch,
                status="INACTIVE",
            ),
            obtained_marks=None,
        )
        ungraded_result.created_at = timezone.make_aware(
            timezone.datetime(2025, 5, 13, 9, 0),
        )
        ungraded_result.save(update_fields=["created_at"])

        other_branch = BranchFactory(school__organization=organization)
        other_teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", is_active=True),
            organization=organization,
            branch=other_branch,
            employee_id="EMP-3001",
        )
        other_academic_year = other_branch.academic_years.get(name="2025/2026")
        other_grade = GradeFactory(
            organization=organization,
            branch=other_branch,
        )
        other_section = SectionFactory(
            organization=organization,
            branch=other_branch,
            grade=other_grade,
            academic_year=other_academic_year,
        )
        other_subject = SubjectFactory(
            organization=organization,
            branch=other_branch,
            grade=other_grade,
        )
        other_assignment = TeacherSubjectAssignment.objects.create(
            teacher=other_teacher,
            organization=organization,
            subject=other_subject,
            section=other_section,
            academic_year=other_academic_year,
        )
        other_assessment = Assessment.objects.create(
            organization=organization,
            branch=other_branch,
            teacher_assignment=other_assignment,
            title="Other Branch Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=Decimal("100.00"),
            passing_marks=Decimal("50.00"),
            due_date=timezone.datetime(2025, 2, 15).date(),
            status=Assessment.Status.PUBLISHED,
        )
        AssessmentResult.objects.create(
            organization=organization,
            assessment=other_assessment,
            student=StudentFactory(
                organization=organization,
                branch=other_branch,
                status="ACTIVE",
            ),
            obtained_marks=Decimal("10.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )

        response = api_client.get(f"/api/branches/{branch.id}/analytics/")

        expected_attendance_rate = 50.0
        expected_parent_linkage_percent = 50.0

        assert response.status_code == status.HTTP_200_OK
        assert response.data["branch_id"] == str(branch.id)
        assert response.data["totals"] == {
            "active_students": 2,
            "active_teachers": 1,
            "active_branch_admins": 1,
        }
        assert response.data["attendance_rate"] == expected_attendance_rate
        assert response.data["performance_risk"] == {
            "at_risk_students": 0,
            "percent": 0.0,
        }
        assert response.data["teacher_count"] == 1
        assert (
            response.data["parent_linkage_percent"] == expected_parent_linkage_percent
        )
        assert response.data["attendance_trend"]["weekly"] == [
            {"year": 2025, "week": 2, "attendance_rate": 50.0},
            {"year": 2025, "week": 6, "attendance_rate": 50.0},
        ]
        assert response.data["attendance_trend"]["monthly"] == [
            {"year": 2025, "month": 1, "attendance_rate": 50.0},
            {"year": 2025, "month": 2, "attendance_rate": 50.0},
        ]
        assert response.data["attendance_trend"]["annual"] == [
            {"year": 2025, "attendance_rate": 50.0},
        ]
        assert response.data["per_grade"] == [
            {
                "grade_id": str(grade.id),
                "grade_name": "Grade 8",
                "student_count": 1,
                "performance_score": 85.0,
            },
            {
                "grade_id": str(second_grade.id),
                "grade_name": "Grade 9",
                "student_count": 1,
                "performance_score": 60.0,
            },
        ]
        assert response.data["academic_performance_index"]["annual"] == [
            {"year": 2025, "average_percentage": 70.0},
            {"year": 2026, "average_percentage": 90.0},
        ]
        assert response.data["academic_performance_index"]["quarterly"] == [
            {"year": 2025, "quarter": 1, "average_percentage": 80.0},
            {"year": 2025, "quarter": 2, "average_percentage": 60.0},
            {"year": 2026, "quarter": 1, "average_percentage": 90.0},
        ]

    def test_analytics_endpoint_returns_empty_series_without_graded_results(
        self,
        api_client: APIClient,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        api_client.force_authenticate(user=owner)

        response = api_client.get(f"/api/branches/{branch.id}/analytics/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["totals"] == {
            "active_students": 0,
            "active_teachers": 0,
            "active_branch_admins": 0,
        }
        assert response.data["attendance_rate"] == 0.0
        assert response.data["performance_risk"] == {
            "at_risk_students": 0,
            "percent": 0.0,
        }
        assert response.data["teacher_count"] == 0
        assert response.data["parent_linkage_percent"] == 0.0
        assert response.data["attendance_trend"] == {
            "weekly": [],
            "monthly": [],
            "annual": [],
        }
        assert response.data["per_grade"] == []
        assert response.data["academic_performance_index"]["annual"] == []
        assert response.data["academic_performance_index"]["quarterly"] == []

    def test_analytics_endpoint_returns_404_for_inaccessible_branch(
        self,
        api_client: APIClient,
    ):
        branch = BranchFactory()
        api_client.force_authenticate(user=UserFactory())

        response = api_client.get(f"/api/branches/{branch.id}/analytics/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_top_performance_risks_returns_ranked_students_and_respects_limit(
        self,
        api_client: APIClient,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        organization = branch.organization
        academic_year = branch.academic_years.get(name="2025/2026")
        api_client.force_authenticate(user=owner)

        grade = GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 10",
            level=10,
        )
        section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="A",
        )
        subject = SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Physics",
            code="PHY-10",
        )
        teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", is_active=True),
            organization=organization,
            branch=branch,
            employee_id="EMP-RISK-1",
        )
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        student_a = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Alpha",
            last_name="Student",
            roll_no="RISK-001",
        )
        student_b = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Beta",
            last_name="Student",
            roll_no="RISK-002",
        )
        student_c = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Gamma",
            last_name="Student",
            roll_no="RISK-003",
        )

        for title, due_date in (
            ("Quiz 1", timezone.datetime(2025, 1, 15).date()),
            ("Quiz 2", timezone.datetime(2025, 2, 15).date()),
            ("Quiz 3", timezone.datetime(2025, 3, 15).date()),
        ):
            Assessment.objects.create(
                organization=organization,
                branch=branch,
                teacher_assignment=assignment,
                title=title,
                task_type=Assessment.TaskType.QUIZ,
                total_marks=Decimal("100.00"),
                passing_marks=Decimal("50.00"),
                due_date=due_date,
                status=Assessment.Status.PUBLISHED,
            )

        assessments = list(
            Assessment.objects.filter(branch=branch).order_by("due_date"),
        )

        low_a_1 = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessments[0],
            student=student_a,
            obtained_marks=Decimal("30.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        low_a_1.created_at = timezone.make_aware(timezone.datetime(2025, 1, 20, 9, 0))
        low_a_1.save(update_fields=["created_at"])

        low_a_2 = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessments[1],
            student=student_a,
            obtained_marks=Decimal("40.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        low_a_2.created_at = timezone.make_aware(timezone.datetime(2025, 2, 20, 9, 0))
        low_a_2.save(update_fields=["created_at"])

        low_b = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessments[2],
            student=student_b,
            obtained_marks=Decimal("35.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        low_b.created_at = timezone.make_aware(timezone.datetime(2025, 3, 20, 9, 0))
        low_b.save(update_fields=["created_at"])

        safe_result = AssessmentResult.objects.create(
            organization=organization,
            assessment=assessments[0],
            student=student_c,
            obtained_marks=Decimal("80.00"),
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )
        safe_result.created_at = timezone.make_aware(
            timezone.datetime(2025, 1, 21, 9, 0),
        )
        safe_result.save(update_fields=["created_at"])

        response = api_client.get(
            f"/api/branches/{branch.id}/top-performance-risks/?limit=2",
        )

        expected_top_risk_count = 2
        expected_average_percentage = 35.0

        assert response.status_code == status.HTTP_200_OK
        assert [item["student_name"] for item in response.data] == [
            "Alpha Student",
            "Beta Student",
        ]
        assert response.data[0]["risk_count"] == expected_top_risk_count
        assert response.data[0]["average_percentage"] == expected_average_percentage
        assert response.data[0]["grade_id"] == str(grade.id)
        assert response.data[0]["grade_name"] == grade.name
        assert response.data[1]["risk_count"] == 1
        assert response.data[1]["average_percentage"] == expected_average_percentage

    def test_top_performance_risks_returns_empty_list_without_low_scores(
        self,
        api_client: APIClient,
    ):
        owner = UserFactory()
        branch = BranchFactory(school__organization__owner=owner)
        api_client.force_authenticate(user=owner)

        response = api_client.get(f"/api/branches/{branch.id}/top-performance-risks/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_top_performance_risks_returns_404_for_inaccessible_branch(
        self,
        api_client: APIClient,
    ):
        branch = BranchFactory()
        api_client.force_authenticate(user=UserFactory())

        response = api_client.get(f"/api/branches/{branch.id}/top-performance-risks/")

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestBranchAdminViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset_scopes_to_request_owner(self, api_rf: APIRequestFactory):
        user = UserFactory()
        owned_branch_admin = BranchAdminFactory(
            branch__school__organization__owner=user,
        )
        foreign_branch_admin = BranchAdminFactory(
            branch__school__organization__owner=UserFactory(),
        )
        view = BranchAdminViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert list(queryset) == [owned_branch_admin]
        assert foreign_branch_admin not in queryset

    def test_get_queryset_includes_same_branch_admins(
        self,
        api_rf: APIRequestFactory,
    ):
        user = UserFactory()
        branch_admin = BranchAdminFactory(user=user)
        same_branch_admin = BranchAdminFactory(branch=branch_admin.branch)
        foreign_branch_admin = BranchAdminFactory()
        view = BranchAdminViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        queryset = view.get_queryset()

        assert set(queryset) == {branch_admin, same_branch_admin}
        assert foreign_branch_admin not in queryset
