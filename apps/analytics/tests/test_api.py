# ruff: noqa: PLR0913, PLR2004

from datetime import timedelta

import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from analytics.models import InterventionLog
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.tests.factories import AttendanceSummaryFactory
from branches.tests.factories import BranchFactory
from django.utils import timezone
from messaging.models import ChatMessage
from messaging.models import ChatThread
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from student_insights.models import StudentInsight
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentAcademicYearSectionFactory
from students.tests.factories import StudentFactory
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment

EXPECTED_OVERALL_GRADE = 80.0
EXPECTED_ATTENDANCE_RATE = 90.48
EXPECTED_COMPLETION_RATE = 60.0
EXPECTED_CLASS_AVERAGE = 67.5
EXPECTED_TREND_DELTA = 15.0
EXPECTED_HEATMAP_CELLS = 28


@pytest.mark.django_db
class TestDashboardOverviewAPI:
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
    def other_academic_year(self, organization, branch):
        return AcademicYear.objects.create(
            organization=organization,
            branch=branch,
            name="2024/2025",
            start_date=timezone.localdate() - timedelta(days=400),
            end_date=timezone.localdate() - timedelta(days=35),
            is_current=False,
        )

    @pytest.fixture
    def grade(self, organization, branch):
        return GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 7",
            level=7,
        )

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
    def subject_math(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Mathematics",
            code="MATH-7",
        )

    @pytest.fixture
    def subject_english(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="English",
            code="ENG-7",
        )

    @pytest.fixture
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Dashboard Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-DASH-1",
            specialization="Mathematics",
        )

    @pytest.fixture
    def other_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Other Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-DASH-2",
            specialization="English",
        )

    def _create_assignment(
        self,
        *,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
    ):
        return TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )

    def _create_assessment(
        self,
        *,
        organization,
        branch,
        assignment,
        title,
        due_date,
        status_value=Assessment.Status.PUBLISHED,
    ):
        return Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title=title,
            task_type=Assessment.TaskType.HOMEWORK,
            total_marks=100,
            due_date=due_date,
            status=status_value,
        )

    def _create_result(
        self,
        *,
        organization,
        assessment,
        student,
        marks,
    ):
        return AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment,
            student=student,
            obtained_marks=marks,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
        )

    def _create_parent_thread(self, *, student, teacher, parent, parent_message_count):
        thread = ChatThread.objects.create(
            parent=parent,
            teacher=teacher,
            student=student,
            organization=student.organization,
            branch=student.branch,
        )
        for index in range(parent_message_count):
            ChatMessage.objects.create(
                thread=thread,
                sender=parent.user,
                text=f"Parent message {index + 1}",
            )
        return thread

    def test_teacher_gets_section_overview_with_subject_filter(
        self,
        api_client,
        organization,
        branch,
        academic_year,
        section,
        other_section,
        subject_math,
        subject_english,
        teacher,
        other_teacher,
    ):
        today = timezone.localdate()
        math_assignment = self._create_assignment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject_math,
            teacher=teacher,
        )
        english_assignment = self._create_assignment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject_english,
            teacher=teacher,
        )
        other_assignment = self._create_assignment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=other_section,
            subject=subject_math,
            teacher=other_teacher,
        )

        student_a = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        student_b = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        student_c = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )
        other_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        for student in (student_a, student_b, student_c):
            StudentAcademicYearSectionFactory(
                student=student,
                academic_year=academic_year,
                section=section,
            )
        StudentAcademicYearSectionFactory(
            student=other_student,
            academic_year=academic_year,
            section=other_section,
        )

        math_homework = self._create_assessment(
            organization=organization,
            branch=branch,
            assignment=math_assignment,
            title="Math Homework",
            due_date=today + timedelta(days=1),
        )
        self._create_assessment(
            organization=organization,
            branch=branch,
            assignment=english_assignment,
            title="English Homework",
            due_date=today + timedelta(days=2),
        )
        self._create_assessment(
            organization=organization,
            branch=branch,
            assignment=other_assignment,
            title="Other Section Homework",
            due_date=today + timedelta(days=1),
        )

        english_quiz = self._create_assessment(
            organization=organization,
            branch=branch,
            assignment=english_assignment,
            title="English Quiz",
            due_date=today - timedelta(days=1),
        )
        other_section_result_assessment = self._create_assessment(
            organization=organization,
            branch=branch,
            assignment=other_assignment,
            title="Other Section Result",
            due_date=today - timedelta(days=2),
        )

        self._create_result(
            organization=organization,
            assessment=math_homework,
            student=student_a,
            marks=90,
        )
        self._create_result(
            organization=organization,
            assessment=math_homework,
            student=student_b,
            marks=72,
        )
        self._create_result(
            organization=organization,
            assessment=math_homework,
            student=student_c,
            marks=55,
        )
        self._create_result(
            organization=organization,
            assessment=english_quiz,
            student=student_a,
            marks=80,
        )
        self._create_result(
            organization=organization,
            assessment=other_section_result_assessment,
            student=other_student,
            marks=20,
        )

        low_parent = ParentFactory(organizations=[organization], branches=[branch])
        moderate_parent = ParentFactory(organizations=[organization], branches=[branch])
        high_parent = ParentFactory(organizations=[organization], branches=[branch])
        ParentStudentLinkFactory(student=student_a, parent=low_parent)
        ParentStudentLinkFactory(student=student_b, parent=moderate_parent)
        ParentStudentLinkFactory(student=student_c, parent=high_parent)
        self._create_parent_thread(
            student=student_a,
            teacher=teacher,
            parent=low_parent,
            parent_message_count=0,
        )
        self._create_parent_thread(
            student=student_b,
            teacher=teacher,
            parent=moderate_parent,
            parent_message_count=1,
        )
        self._create_parent_thread(
            student=student_c,
            teacher=teacher,
            parent=high_parent,
            parent_message_count=3,
        )

        api_client.force_authenticate(user=teacher.user)
        response = api_client.get(
            "/api/dashboard/overview/",
            {
                "section_id": str(section.id),
                "academic_year_id": str(academic_year.id),
                "subject_id": str(subject_math.id),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "total_students": 3,
            "average_performance": 72.33,
            "tasks_due": 1,
            "performance_distribution": {
                "A": 1,
                "B": 1,
                "C": 1,
                "F": 0,
            },
            "parent_engagement": {
                "high": 1,
                "moderate": 1,
                "low": 1,
            },
        }

    def test_teacher_cannot_access_unassigned_section(
        self,
        api_client,
        academic_year,
        other_section,
        teacher,
    ):
        api_client.force_authenticate(user=teacher.user)

        response = api_client.get(
            "/api/dashboard/overview/",
            {
                "section_id": str(other_section.id),
                "academic_year_id": str(academic_year.id),
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_endpoint_rejects_mismatched_academic_year(
        self,
        api_client,
        section,
        academic_year,
        other_academic_year,
        teacher,
        organization,
        branch,
        subject_math,
    ):
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject_math,
            section=section,
            academic_year=academic_year,
        )
        api_client.force_authenticate(user=teacher.user)

        response = api_client.get(
            "/api/dashboard/overview/",
            {
                "section_id": str(section.id),
                "academic_year_id": str(other_academic_year.id),
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "does not match the section" in response.data["detail"]


@pytest.mark.django_db
class TestInterventionLogTeacherAccessAPI:
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
        return GradeFactory(organization=organization, branch=branch, level=9)

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
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Assigned Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-IL-1",
            specialization="English",
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

    @pytest.fixture(autouse=True)
    def setup_assignment(
        self,
        organization,
        academic_year,
        subject,
        section,
        teacher,
    ):
        TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )

    def test_teacher_can_list_retrieve_and_update_logs_for_assigned_students(
        self,
        api_client,
        teacher,
        organization,
        student,
    ):
        log = InterventionLog.objects.create(
            organization=organization,
            student=student,
            intervention_type=InterventionLog.InterventionType.LOW_GRADE,
            severity=InterventionLog.Severity.MEDIUM,
            status=InterventionLog.Status.OPEN,
            title="Low grade alert",
            description="Needs review",
        )
        api_client.force_authenticate(user=teacher.user)

        list_response = api_client.get("/api/intervention-logs/")
        retrieve_response = api_client.get(f"/api/intervention-logs/{log.id}/")
        patch_response = api_client.patch(
            f"/api/intervention-logs/{log.id}/",
            {
                "status": InterventionLog.Status.IN_PROGRESS,
                "description": "Teacher is following up",
            },
            format="json",
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 1
        assert list_response.data["results"][0]["id"] == str(log.id)
        assert retrieve_response.status_code == status.HTTP_200_OK
        assert retrieve_response.data["id"] == str(log.id)
        assert patch_response.status_code == status.HTTP_200_OK
        assert patch_response.data["status"] == InterventionLog.Status.IN_PROGRESS

    def test_teacher_cannot_access_or_update_unassigned_logs(
        self,
        api_client,
        teacher,
        organization,
        other_student,
    ):
        log = InterventionLog.objects.create(
            organization=organization,
            student=other_student,
            intervention_type=InterventionLog.InterventionType.ATTENDANCE,
            severity=InterventionLog.Severity.HIGH,
            status=InterventionLog.Status.OPEN,
            title="Attendance concern",
            description="Too many absences",
        )
        api_client.force_authenticate(user=teacher.user)

        list_response = api_client.get("/api/intervention-logs/")
        retrieve_response = api_client.get(f"/api/intervention-logs/{log.id}/")
        patch_response = api_client.patch(
            f"/api/intervention-logs/{log.id}/",
            {"status": InterventionLog.Status.RESOLVED},
            format="json",
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 0
        assert retrieve_response.status_code == status.HTTP_404_NOT_FOUND
        assert patch_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestStudentAnalyticsAPI:
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
        return GradeFactory(
            organization=organization,
            branch=branch,
            name="Grade 6",
            level=6,
        )

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
    def subject_math(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Mathematics",
            code="MATH-6",
        )

    @pytest.fixture
    def subject_english(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="English",
            code="ENG-6",
        )

    @pytest.fixture
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Ms. Hana"),
            organization=organization,
            branch=branch,
            employee_id="EMP-SA-1",
            specialization="General",
        )

    @pytest.fixture
    def student(self, organization, branch, section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

    @pytest.fixture
    def classmate(self, organization, branch, section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
        )

    @pytest.fixture
    def parent(self, student):
        parent = ParentFactory(
            organizations=[student.organization],
            branches=[student.branch],
        )
        ParentStudentLinkFactory(
            student=student,
            parent=parent,
            relationship_type="MOTHER",
        )
        return parent

    @pytest.fixture
    def other_parent_user(self):
        parent = ParentFactory()
        return parent.user

    @pytest.fixture(autouse=True)
    def setup_assignments(
        self,
        organization,
        academic_year,
        section,
        subject_math,
        subject_english,
        teacher,
    ):
        math_assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject_math,
            section=section,
            academic_year=academic_year,
        )
        english_assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject_english,
            section=section,
            academic_year=academic_year,
        )
        return {
            "math": math_assignment,
            "english": english_assignment,
        }

    def _create_result(
        self,
        *,
        assignment,
        student,
        obtained_marks,
        total_marks,
        submission_status,
        created_at,
        title,
    ):
        assessment = Assessment.objects.create(
            organization=student.organization,
            branch=student.branch,
            teacher_assignment=assignment,
            title=title,
            task_type=Assessment.TaskType.ASSIGNMENT,
            total_marks=total_marks,
            passing_marks=total_marks / 2,
            status=Assessment.Status.PUBLISHED,
        )
        result = AssessmentResult.objects.create(
            organization=student.organization,
            assessment=assessment,
            student=student,
            obtained_marks=obtained_marks,
            submission_status=submission_status,
        )
        AssessmentResult.objects.filter(id=result.id).update(created_at=created_at)
        result.refresh_from_db()
        return result

    def test_parent_can_fetch_aggregated_student_analytics(
        self,
        api_client,
        parent,
        student,
        classmate,
        academic_year,
        setup_assignments,
    ):
        now = timezone.now()
        self._create_result(
            assignment=setup_assignments["math"],
            student=student,
            obtained_marks=80,
            total_marks=100,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            created_at=now - timedelta(days=20),
            title="Quiz 1",
        )
        self._create_result(
            assignment=setup_assignments["english"],
            student=student,
            obtained_marks=70,
            total_marks=100,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            created_at=now - timedelta(days=12),
            title="Essay 1",
        )
        self._create_result(
            assignment=setup_assignments["math"],
            student=student,
            obtained_marks=90,
            total_marks=100,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            created_at=now - timedelta(days=3),
            title="Quiz 2",
        )
        pending_assessment = Assessment.objects.create(
            organization=student.organization,
            branch=student.branch,
            teacher_assignment=setup_assignments["english"],
            title="Essay 2",
            task_type=Assessment.TaskType.ASSIGNMENT,
            total_marks=100,
            passing_marks=50,
            status=Assessment.Status.PUBLISHED,
        )
        AssessmentResult.objects.create(
            organization=student.organization,
            assessment=pending_assessment,
            student=student,
            submission_status=AssessmentResult.SubmissionStatus.PENDING,
        )
        missing_assessment = Assessment.objects.create(
            organization=student.organization,
            branch=student.branch,
            teacher_assignment=setup_assignments["math"],
            title="Worksheet",
            task_type=Assessment.TaskType.HOMEWORK,
            total_marks=50,
            passing_marks=25,
            status=Assessment.Status.PUBLISHED,
        )
        AssessmentResult.objects.create(
            organization=student.organization,
            assessment=missing_assessment,
            student=student,
            submission_status=AssessmentResult.SubmissionStatus.MISSING,
        )
        self._create_result(
            assignment=setup_assignments["math"],
            student=classmate,
            obtained_marks=60,
            total_marks=100,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            created_at=now - timedelta(days=10),
            title="Quiz 1",
        )
        self._create_result(
            assignment=setup_assignments["english"],
            student=classmate,
            obtained_marks=50,
            total_marks=100,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            created_at=now - timedelta(days=2),
            title="Essay 1",
        )
        AttendanceSummaryFactory(
            organization=student.organization,
            student=student,
            academic_year=academic_year,
            total_present=18,
            total_absent=1,
            total_late=1,
            total_excused=1,
            total_school_days=21,
        )
        StudentInsight.objects.create(
            organization=student.organization,
            branch=student.branch,
            student=student,
            source_event_type=StudentInsight.SourceEventType.ASSESSMENT_RESULT,
            source_model="assessments.AssessmentResult",
            source_id=None,
            dedupe_key="analytics:test",
            category=StudentInsight.Category.ACADEMICS,
            risk_band=StudentInsight.RiskBand.MEDIUM,
            title="Math progress improved this week",
            message="Recent math scores improved after the last assignment.",
            recommended_actions=[
                "Ask your child what helped on the latest math task.",
                "Keep a short review routine before the next assessment.",
            ],
            confidence_label="RULE_BASED",
            safety_status=StudentInsight.SafetyStatus.APPROVED,
            delivery_status=StudentInsight.DeliveryStatus.DELIVERED,
        )

        api_client.force_authenticate(user=parent.user)
        response = api_client.get(f"/api/v1/student-analytics/{student.id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"]["student_id"] == str(student.id)
        assert (
            response.data["data"]["analysis_window_label"]
            == "Current term · Last 4 weeks of activity"
        )

        summary = response.data["data"]["summary"]
        assert summary["overall_grade"] == EXPECTED_OVERALL_GRADE
        assert summary["attendance_rate"] == EXPECTED_ATTENDANCE_RATE
        assert summary["assignment_completion_rate"] == EXPECTED_COMPLETION_RATE
        assert summary["completed_assignments"] == 3
        assert summary["pending_assignments"] == 1
        assert summary["missing_assignments"] == 1
        assert summary["class_average_overall"] == EXPECTED_CLASS_AVERAGE
        assert summary["class_rank"] == 1
        assert summary["class_size"] == 2
        assert summary["risk_band"] == "medium"
        assert summary["trend_direction"] == "up"
        assert summary["trend_delta"] == EXPECTED_TREND_DELTA
        assert summary["headline_insight"] == "Math progress improved this week"

        subject_rows = response.data["data"]["subject_performance"]
        assert len(subject_rows) == 2
        assert subject_rows[0]["teacher_name"] == "Ms. Hana"

        trend_series = response.data["data"]["grade_trend"]["series"]
        assert len(trend_series) == 2
        assert trend_series[0]["points"]

        heatmap = response.data["data"]["submission_heatmap"]
        assert len(heatmap) == EXPECTED_HEATMAP_CELLS
        assert all("submission_count" in cell for cell in heatmap)
        assert sum(cell["submission_count"] for cell in heatmap) == 3

        assert response.data["data"]["recommended_actions"] == [
            "Ask your child what helped on the latest math task.",
            "Keep a short review routine before the next assessment.",
        ]

    def test_parent_gets_404_for_unlinked_child(
        self,
        api_client,
        other_parent_user,
        student,
    ):
        api_client.force_authenticate(user=other_parent_user)

        response = api_client.get(f"/api/v1/student-analytics/{student.id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_parent_cannot_access_student_analytics(self, api_client, student):
        teacher_user = UserFactory(role="TEACHER")
        api_client.force_authenticate(user=teacher_user)

        response = api_client.get(f"/api/v1/student-analytics/{student.id}/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_heatmap_always_returns_28_cells_when_no_activity(
        self,
        api_client,
        parent,
        student,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.get(f"/api/v1/student-analytics/{student.id}/")

        assert response.status_code == status.HTTP_200_OK
        heatmap = response.data["data"]["submission_heatmap"]
        assert len(heatmap) == EXPECTED_HEATMAP_CELLS
        assert all(cell["submission_count"] == 0 for cell in heatmap)
