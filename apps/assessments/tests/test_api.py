from datetime import date
from datetime import timedelta

import pytest
from academics.models import AcademicYear
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from assessments.models import Assessment
from assessments.models import AssessmentResult
from assessments.models import HomeworkConfirmation
from branches.tests.factories import BranchAdminFactory
from branches.tests.factories import BranchFactory
from django.core.exceptions import ValidationError
from django.utils import timezone
from organizations.tests.factories import OrganizationFactory
from rest_framework import status
from rest_framework.test import APIClient
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment


@pytest.mark.django_db
class TestAssessmentsAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def owner(self):
        return UserFactory()

    @pytest.fixture
    def organization(self, owner):
        return OrganizationFactory(owner=owner)

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
    def subject(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Mathematics",
            code="MATH-7",
        )

    @pytest.fixture
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Abel"),
            organization=organization,
            branch=branch,
            employee_id="EMP-1001",
            specialization="Mathematics",
        )

    def test_list_can_filter_by_teacher_section_and_subject(
        self,
        api_client,
        owner,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
    ):
        api_client.force_authenticate(user=owner)

        matching_assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        matching_assessment = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=matching_assignment,
            title="Algebra Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=20,
            passing_marks=10,
            due_date=date(2026, 1, 15),
            status=Assessment.Status.PUBLISHED,
        )

        other_teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Beth"),
            organization=organization,
            branch=branch,
            employee_id="EMP-1002",
            specialization="Physics",
        )
        other_assignment = TeacherSubjectAssignment.objects.create(
            teacher=other_teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=other_assignment,
            title="Geometry Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=20,
            passing_marks=10,
            due_date=date(2026, 1, 16),
            status=Assessment.Status.PUBLISHED,
        )

        response = api_client.get(
            "/api/assessments/",
            {
                "teacher": str(teacher.id),
                "section": str(section.id),
                "subject": str(subject.id),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(matching_assessment.id)
        assert str(response.data["results"][0]["teacher_assignment"]) == str(
            matching_assignment.id,
        )
        assert response.data["results"][0]["teacher_name"] == "Abel"
        assert response.data["results"][0]["section_name"] == section.name
        assert response.data["results"][0]["subject_name"] == subject.name

    def test_teacher_can_fetch_own_assessments_by_filters(
        self,
        api_client,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
    ):
        api_client.force_authenticate(user=teacher.user)

        matching_assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        matching_assessment = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=matching_assignment,
            title="Teacher Visible Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=25,
            passing_marks=12,
            due_date=date(2026, 1, 20),
            status=Assessment.Status.PUBLISHED,
        )

        other_teacher = Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Beth"),
            organization=organization,
            branch=branch,
            employee_id="EMP-1002",
            specialization="Physics",
        )
        other_assignment = TeacherSubjectAssignment.objects.create(
            teacher=other_teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=other_assignment,
            title="Teacher Hidden Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=25,
            passing_marks=12,
            due_date=date(2026, 1, 21),
            status=Assessment.Status.PUBLISHED,
        )

        response = api_client.get(
            "/api/assessments/",
            {
                "teacher": str(teacher.id),
                "section": str(section.id),
                "subject": str(subject.id),
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(matching_assessment.id)
        assert response.data["results"][0]["teacher_name"] == "Abel"


@pytest.mark.django_db
class TestAssessmentResultsTeacherAccessAPI:
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
            name="Grade 8",
            level=8,
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
    def subject(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Physics",
            code="PHY-8",
        )

    @pytest.fixture
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Assigned Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-AR-1",
            specialization="Physics",
        )

    @pytest.fixture
    def other_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Other Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-AR-2",
            specialization="Chemistry",
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
    def assessment(
        self,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
    ):
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        return Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Assigned Teacher Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=20,
            passing_marks=10,
            due_date=date(2026, 2, 1),
            status=Assessment.Status.PUBLISHED,
        )

    @pytest.fixture
    def other_assessment(
        self,
        organization,
        branch,
        academic_year,
        other_section,
        subject,
        other_teacher,
    ):
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=other_teacher,
            organization=organization,
            subject=subject,
            section=other_section,
            academic_year=academic_year,
        )
        return Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Other Teacher Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=20,
            passing_marks=10,
            due_date=date(2026, 2, 2),
            status=Assessment.Status.PUBLISHED,
        )

    def test_assigned_teacher_can_read_results_for_own_assessment(
        self,
        api_client,
        teacher,
        assessment,
        student,
    ):
        result = AssessmentResult.objects.create(
            organization=assessment.organization,
            assessment=assessment,
            student=student,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            obtained_marks=18,
        )
        api_client.force_authenticate(user=teacher.user)

        list_response = api_client.get(
            "/api/assessment-results/",
            {"assessment": str(assessment.id)},
        )
        by_assessment_response = api_client.get(
            "/api/assessment-results/by-assessment/",
            {"assessment": str(assessment.id)},
        )
        by_student_response = api_client.get(
            "/api/assessment-results/by-student/",
            {"student": str(student.id)},
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 1
        assert list_response.data["results"][0]["id"] == str(result.id)
        assert list_response.data["results"][0]["task_type"] == Assessment.TaskType.QUIZ
        assert list_response.data["results"][0]["task_type_display"] == "Quiz"
        assert by_assessment_response.status_code == status.HTTP_200_OK
        assert by_assessment_response.data[0]["id"] == str(result.id)
        assert by_student_response.status_code == status.HTTP_200_OK
        assert by_student_response.data[0]["id"] == str(result.id)
        assert by_student_response.data[0]["task_type"] == Assessment.TaskType.QUIZ

    def test_assigned_teacher_can_create_and_bulk_grade_own_results(
        self,
        api_client,
        teacher,
        assessment,
        student,
    ):
        api_client.force_authenticate(user=teacher.user)

        create_response = api_client.post(
            "/api/assessment-results/",
            {
                "organization": str(assessment.organization_id),
                "assessment": str(assessment.id),
                "student": str(student.id),
                "obtained_marks": "15.00",
                "submission_status": AssessmentResult.SubmissionStatus.GRADED,
                "feedback": "Good work",
            },
            format="json",
        )
        bulk_response = api_client.post(
            "/api/assessment-results/bulk-grade/",
            {
                "assessment": str(assessment.id),
                "results": [
                    {
                        "student": str(student.id),
                        "obtained_marks": "16.00",
                        "submission_status": AssessmentResult.SubmissionStatus.GRADED,
                        "feedback": "Updated",
                    },
                ],
            },
            format="json",
        )

        assert create_response.status_code == status.HTTP_201_CREATED
        assert create_response.data["graded_by"] == teacher.user.id
        assert bulk_response.status_code == status.HTTP_200_OK
        assert bulk_response.data["updated"] == 1

    def test_teacher_cannot_read_or_write_other_teachers_results(
        self,
        api_client,
        teacher,
        other_assessment,
        other_student,
        organization,
        branch,
        other_section,
    ):
        AssessmentResult.objects.create(
            organization=other_assessment.organization,
            assessment=other_assessment,
            student=other_student,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            obtained_marks=11,
        )
        another_other_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        api_client.force_authenticate(user=teacher.user)

        list_response = api_client.get(
            "/api/assessment-results/",
            {"assessment": str(other_assessment.id)},
        )
        by_assessment_response = api_client.get(
            "/api/assessment-results/by-assessment/",
            {"assessment": str(other_assessment.id)},
        )
        create_response = api_client.post(
            "/api/assessment-results/",
            {
                "organization": str(other_assessment.organization_id),
                "assessment": str(other_assessment.id),
                "student": str(another_other_student.id),
                "obtained_marks": "9.00",
                "submission_status": AssessmentResult.SubmissionStatus.GRADED,
            },
            format="json",
        )
        bulk_response = api_client.post(
            "/api/assessment-results/bulk-grade/",
            {
                "assessment": str(other_assessment.id),
                "results": [
                    {
                        "student": str(other_student.id),
                        "obtained_marks": "9.00",
                        "submission_status": AssessmentResult.SubmissionStatus.GRADED,
                    },
                ],
            },
            format="json",
        )

        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.data["count"] == 0
        assert by_assessment_response.status_code == status.HTTP_200_OK
        assert by_assessment_response.data == []
        assert create_response.status_code == status.HTTP_403_FORBIDDEN
        assert bulk_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTodaysHomeworkAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def owner(self):
        return UserFactory()

    @pytest.fixture
    def organization(self, owner):
        return OrganizationFactory(owner=owner)

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
            user=UserFactory(role="TEACHER", name="Homework Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-HW-1",
            specialization="English",
        )

    @pytest.fixture
    def other_teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Other Homework Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-HW-2",
            specialization="Science",
        )

    @pytest.fixture
    def student(self, organization, branch, section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=section,
            first_name="Liya",
            last_name="Bekele",
        )

    @pytest.fixture
    def other_student(self, organization, branch, other_section):
        return StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
            first_name="Noah",
            last_name="Abebe",
        )

    @pytest.fixture
    def parent(self, organization, branch):
        return ParentFactory(
            organizations=[organization],
            branches=[branch],
        )

    @pytest.fixture
    def linked_parent(self, parent, student):
        return ParentStudentLinkFactory(
            parent=parent,
            student=student,
            relationship_type="MOTHER",
        )

    @pytest.fixture
    def branch_admin(self, organization, branch):
        return BranchAdminFactory(
            organization=organization,
            branch=branch,
            user=UserFactory(role="BRANCH_ADMIN"),
        )

    def _create_homework_assessment(
        self,
        *,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
        student,
        due_date,
        title="Homework",
        create_result=True,
    ):
        assignment, _created = TeacherSubjectAssignment.objects.get_or_create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        assessment = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title=title,
            task_type=Assessment.TaskType.HOMEWORK,
            total_marks=10,
            passing_marks=5,
            due_date=due_date,
            status=Assessment.Status.PUBLISHED,
            description="Read chapter 2",
        )
        if create_result:
            AssessmentResult.objects.create(
                organization=organization,
                assessment=assessment,
                student=student,
                submission_status=AssessmentResult.SubmissionStatus.PENDING,
            )
        return assessment

    def test_parent_gets_only_linked_students_homework_due_today(
        self,
        api_client,
        organization,
        branch,
        academic_year,
        section,
        other_section,
        subject,
        teacher,
        student,
        other_student,
        parent,
        linked_parent,
    ):
        today = timezone.localdate()
        visible_assessment = self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=student,
            due_date=today,
            title="Visible Homework",
        )
        self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=other_section,
            subject=subject,
            teacher=teacher,
            student=other_student,
            due_date=today,
            title="Hidden Homework",
        )
        api_client.force_authenticate(user=parent.user)

        response = api_client.get("/api/assessments/todays-homework/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        item = response.data["results"][0]
        assert item["id"] == str(visible_assessment.id)
        assert item["student_name"] == "Liya Bekele"
        assert item["title"] == "Visible Homework"
        assert item["teacher_name"] == teacher.user.name
        assert item["homework_confirmation"] is None

    def test_teacher_gets_only_own_section_homework_due_today(
        self,
        api_client,
        organization,
        branch,
        academic_year,
        section,
        other_section,
        subject,
        teacher,
        other_teacher,
        student,
        other_student,
    ):
        today = timezone.localdate()
        own_assessment = self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=student,
            due_date=today,
            title="Own Homework",
        )
        self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=other_section,
            subject=subject,
            teacher=other_teacher,
            student=other_student,
            due_date=today,
            title="Other Homework",
        )
        api_client.force_authenticate(user=teacher.user)

        response = api_client.get("/api/assessments/todays-homework/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(own_assessment.id)

    def test_branch_admin_gets_scoped_homework_and_non_today_is_excluded(
        self,
        api_client,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
        student,
        branch_admin,
    ):
        today = timezone.localdate()
        expected_assessment = self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=student,
            due_date=today,
            title="Today Homework",
        )
        self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=StudentFactory(
                organization=organization,
                branch=branch,
                current_section=section,
            ),
            due_date=today - timedelta(days=1),
            title="Old Homework",
        )
        api_client.force_authenticate(user=branch_admin.user)

        response = api_client.get("/api/assessments/todays-homework/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(expected_assessment.id)

    def test_today_endpoint_can_filter_by_confirmation_state(
        self,
        api_client,
        owner,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
        student,
    ):
        today = timezone.localdate()
        confirmed_assessment = self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=student,
            due_date=today,
            title="Confirmed Homework",
        )
        unconfirmed_assessment = self._create_homework_assessment(
            organization=organization,
            branch=branch,
            academic_year=academic_year,
            section=section,
            subject=subject,
            teacher=teacher,
            student=StudentFactory(
                organization=organization,
                branch=branch,
                current_section=section,
            ),
            due_date=today,
            title="Pending Homework",
        )
        HomeworkConfirmation.objects.create(
            organization=organization,
            branch=branch,
            section=section,
            assessment=confirmed_assessment,
            student=student,
            is_confirmed=True,
            confirmed_at=timezone.now(),
            confirmed_by=owner,
            feedback="Done",
        )
        api_client.force_authenticate(user=owner)

        response = api_client.get(
            "/api/assessments/todays-homework/",
            {"confirmed": "true"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(confirmed_assessment.id)
        assert (
            response.data["results"][0]["homework_confirmation"]["feedback"] == "Done"
        )
        assert str(unconfirmed_assessment.id) not in {
            item["id"] for item in response.data["results"]
        }


@pytest.mark.django_db
class TestHomeworkConfirmationAPI:
    @pytest.fixture
    def api_client(self):
        return APIClient()

    @pytest.fixture
    def owner(self):
        return UserFactory()

    @pytest.fixture
    def organization(self, owner):
        return OrganizationFactory(owner=owner)

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
            name="Grade 5",
            level=5,
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
    def subject(self, organization, branch, grade):
        return SubjectFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            name="Science",
            code="SCI-5",
        )

    @pytest.fixture
    def teacher(self, organization, branch):
        return Teacher.objects.create(
            user=UserFactory(role="TEACHER", name="Science Teacher"),
            organization=organization,
            branch=branch,
            employee_id="EMP-CF-1",
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
    def homework_result(
        self,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
        student,
    ):
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        assessment = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Science Homework",
            task_type=Assessment.TaskType.HOMEWORK,
            total_marks=10,
            passing_marks=5,
            due_date=timezone.localdate(),
            status=Assessment.Status.PUBLISHED,
        )
        return AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment,
            student=student,
        )

    @pytest.fixture
    def quiz_result(
        self,
        organization,
        branch,
        academic_year,
        section,
        subject,
        teacher,
        student,
    ):
        assignment = TeacherSubjectAssignment.objects.create(
            teacher=teacher,
            organization=organization,
            subject=subject,
            section=section,
            academic_year=academic_year,
        )
        assessment = Assessment.objects.create(
            organization=organization,
            branch=branch,
            teacher_assignment=assignment,
            title="Science Quiz",
            task_type=Assessment.TaskType.QUIZ,
            total_marks=10,
            passing_marks=5,
            due_date=timezone.localdate(),
            status=Assessment.Status.PUBLISHED,
        )
        return AssessmentResult.objects.create(
            organization=organization,
            assessment=assessment,
            student=student,
        )

    def test_post_confirmation_creates_record_without_touching_legacy_summary_fields(
        self,
        api_client,
        parent,
        homework_result,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.post(
            "/api/homework-confirmations/",
            {
                "assessment": str(homework_result.assessment_id),
                "student": str(homework_result.student_id),
                "is_confirmed": True,
                "feedback": "Completed after dinner",
            },
            format="json",
        )

        homework_result.refresh_from_db()
        confirmation = HomeworkConfirmation.objects.get(
            assessment=homework_result.assessment,
            student=homework_result.student,
        )
        assert response.status_code == status.HTTP_200_OK
        assert confirmation.feedback == "Completed after dinner"
        assert homework_result.parent_confirmed is False
        assert homework_result.parent_confirmed_by is None
        assert homework_result.parent_confirmed_at is None

    def test_reposting_updates_existing_confirmation_instead_of_creating_second(
        self,
        api_client,
        parent,
        homework_result,
    ):
        api_client.force_authenticate(user=parent.user)
        first_response = api_client.post(
            "/api/homework-confirmations/",
            {
                "assessment": str(homework_result.assessment_id),
                "student": str(homework_result.student_id),
                "is_confirmed": True,
                "feedback": "Initial note",
            },
            format="json",
        )
        first_id = first_response.data["id"]

        second_response = api_client.post(
            "/api/homework-confirmations/",
            {
                "assessment": str(homework_result.assessment_id),
                "student": str(homework_result.student_id),
                "is_confirmed": True,
                "feedback": "Updated note",
            },
            format="json",
        )

        assert second_response.status_code == status.HTTP_200_OK
        assert HomeworkConfirmation.objects.count() == 1
        assert second_response.data["id"] == first_id
        assert HomeworkConfirmation.objects.get().feedback == "Updated note"

    def test_non_homework_result_cannot_be_confirmed(
        self,
        api_client,
        parent,
        quiz_result,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.post(
            "/api/homework-confirmations/",
            {
                "assessment": str(quiz_result.assessment_id),
                "student": str(quiz_result.student_id),
                "is_confirmed": True,
                "feedback": "Should fail",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert HomeworkConfirmation.objects.count() == 0

    def test_user_without_access_gets_forbidden(
        self,
        api_client,
        homework_result,
    ):
        api_client.force_authenticate(user=UserFactory(role="PARENT"))

        response = api_client.post(
            "/api/homework-confirmations/",
            {
                "assessment": str(homework_result.assessment_id),
                "student": str(homework_result.student_id),
                "is_confirmed": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_parent_can_confirm_homework_via_detail_action(
        self,
        api_client,
        parent,
        homework_result,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.patch(
            f"/api/assessment-results/{homework_result.id}/confirm-homework/",
            {
                "parent_confirmed": True,
                "feedback": "Completed after dinner",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert HomeworkConfirmation.objects.count() == 1
        confirmation = HomeworkConfirmation.objects.get(
            assessment=homework_result.assessment,
            student=homework_result.student,
        )
        assert confirmation.is_confirmed is True
        assert confirmation.feedback == "Completed after dinner"
        assert confirmation.confirmed_by == parent.user

    def test_unlinked_parent_cannot_confirm_homework_via_detail_action(
        self,
        api_client,
        homework_result,
    ):
        api_client.force_authenticate(user=ParentFactory().user)

        response = api_client.patch(
            f"/api/assessment-results/{homework_result.id}/confirm-homework/",
            {"parent_confirmed": True},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_non_homework_result_cannot_be_confirmed_via_detail_action(
        self,
        api_client,
        parent,
        quiz_result,
    ):
        api_client.force_authenticate(user=parent.user)

        response = api_client.patch(
            f"/api/assessment-results/{quiz_result.id}/confirm-homework/",
            {
                "parent_confirmed": True,
                "feedback": "Should fail",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert HomeworkConfirmation.objects.count() == 0

    def test_model_clean_rejects_mismatched_confirmation_context(
        self,
        organization,
        branch,
        academic_year,
        grade,
        section,
        homework_result,
        owner,
    ):
        other_section = SectionFactory(
            organization=organization,
            branch=branch,
            grade=grade,
            academic_year=academic_year,
            name="B",
        )
        other_student = StudentFactory(
            organization=organization,
            branch=branch,
            current_section=other_section,
        )
        confirmation = HomeworkConfirmation(
            organization=organization,
            branch=branch,
            section=section,
            assessment=homework_result.assessment,
            student=other_student,
            is_confirmed=True,
            confirmed_by=owner,
        )

        with pytest.raises(ValidationError):
            confirmation.full_clean()
