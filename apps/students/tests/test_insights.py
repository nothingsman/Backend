from __future__ import annotations

from datetime import date

import pytest
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from academics.utils import get_or_create_academic_year_for_branch
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from messaging.models import ChatMessage
from messaging.tests.factories import ChatThreadFactory
from messaging.tests.factories import TeacherFactory
from notifications.models import Notification
from rest_framework import status
from rest_framework.test import APIClient
from students.services.insights import NO_QUALIFYING_SIGNAL_MESSAGE
from students.services.insights import NO_QUALIFYING_SIGNAL_REASON
from students.services.insights import GeminiGenerationError
from students.services.insights import GeneratedInsight
from students.services.insights import select_latest_qualifying_signal
from students.services.insights import trigger_student_insight_demo
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import TeacherSubjectAssignment


def _build_student_context():
    parent = ParentFactory()
    organization = parent.organizations.first()
    branch = parent.branches.first()
    academic_year, _ = get_or_create_academic_year_for_branch(branch)
    grade = GradeFactory(
        organization=organization,
        branch=branch,
    )
    section = SectionFactory(
        organization=organization,
        branch=branch,
        grade=grade,
        academic_year=academic_year,
    )
    student = StudentFactory(
        organization=organization,
        branch=branch,
        current_section=section,
    )
    ParentStudentLinkFactory(
        parent=parent,
        student=student,
        is_primary_contact=True,
    )
    teacher = TeacherFactory(_student=student)
    subject = SubjectFactory(
        organization=organization,
        branch=branch,
        grade=grade,
    )
    teacher_assignment = TeacherSubjectAssignment.objects.create(
        teacher=teacher,
        organization=organization,
        subject=subject,
        section=section,
        academic_year=academic_year,
    )
    return {
        "parent": parent,
        "teacher": teacher,
        "student": student,
        "section": section,
        "subject": subject,
        "teacher_assignment": teacher_assignment,
        "organization": organization,
        "branch": branch,
        "academic_year": academic_year,
    }


def _create_low_grade_result(context) -> AssessmentResult:
    assessment = Assessment.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        teacher_assignment=context["teacher_assignment"],
        title="Fractions Quiz",
        task_type=Assessment.TaskType.QUIZ,
        description="Quiz",
        total_marks=10,
        passing_marks=6,
        due_date=date(2026, 6, 4),
        status=Assessment.Status.PUBLISHED,
    )
    result = AssessmentResult.objects.create(
        organization=context["organization"],
        assessment=assessment,
        student=context["student"],
        submission_status=AssessmentResult.SubmissionStatus.GRADED,
        obtained_marks=4,
    )
    Notification.objects.filter(notifiable_id=str(result.id)).delete()
    return result


def _create_homework_issue(context) -> AssessmentResult:
    assessment = Assessment.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        teacher_assignment=context["teacher_assignment"],
        title="Practice Set",
        task_type=Assessment.TaskType.HOMEWORK,
        description="Homework",
        total_marks=10,
        passing_marks=5,
        due_date=date(2026, 6, 5),
        status=Assessment.Status.PUBLISHED,
    )
    return AssessmentResult.objects.create(
        organization=context["organization"],
        assessment=assessment,
        student=context["student"],
        submission_status=AssessmentResult.SubmissionStatus.MISSING,
        parent_confirmed=False,
    )


def _create_attendance_issue(context) -> Attendance:
    return Attendance.objects.create(
        organization=context["organization"],
        branch=context["branch"],
        academic_year=context["academic_year"],
        section=context["section"],
        student=context["student"],
        recorded_by=context["teacher"].user,
        date=date(2026, 6, 3),
        status=Attendance.Status.ABSENT,
        remarks="No note yet",
    )


def _create_teacher_message(context) -> ChatMessage:
    thread = ChatThreadFactory(
        student=context["student"],
        parent=context["parent"],
        teacher=context["teacher"],
        organization=context["organization"],
        branch=context["branch"],
    )
    return ChatMessage.objects.create(
        thread=thread,
        sender=context["teacher"].user,
        text="Please review the recent performance drop.",
    )


@pytest.mark.django_db
def test_select_latest_qualifying_signal_prefers_low_grade_before_other_signals():
    context = _build_student_context()
    low_grade = _create_low_grade_result(context)
    _create_homework_issue(context)
    _create_attendance_issue(context)
    _create_teacher_message(context)

    signal = select_latest_qualifying_signal(context["student"])

    assert signal is not None
    assert signal.source_event_type == "ASSESSMENT_RESULT"
    assert signal.source_id == str(low_grade.id)


@pytest.mark.django_db
def test_trigger_student_insight_demo_uses_rule_based_fallback_when_gemini_fails(
    monkeypatch: pytest.MonkeyPatch,
    settings,
):
    context = _build_student_context()
    _create_low_grade_result(context)
    settings.GEMINI_API_KEY = "bad-key"

    def fail_gemini(signal):
        del signal
        error_message = "boom"
        raise GeminiGenerationError(error_message)

    def fallback(signal):
        return GeneratedInsight(
            title="Fallback title",
            message="Fallback body",
            category=signal.category,
            risk_band=signal.risk_band,
            delivery_status="DELIVERED",
            data={"channel": "notification"},
            generated_by="rule_based",
        )

    monkeypatch.setattr(
        "students.services.insights._generate_with_gemini",
        fail_gemini,
    )
    monkeypatch.setattr(
        "students.services.insights._build_rule_based_insight",
        fallback,
    )

    payload = trigger_student_insight_demo(context["student"])

    notification = Notification.objects.get(id=payload["insight_id"])
    assert payload["created"] is True
    assert payload["reused_existing"] is False
    assert notification.data["generated_by"] == "rule_based"
    assert notification.data["category"] == "ACADEMICS"
    assert notification.data["source_event_type"] == "ASSESSMENT_RESULT"


@pytest.mark.django_db
def test_trigger_student_insight_demo_does_not_call_rule_based_when_gemini_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    settings,
):
    context = _build_student_context()
    _create_low_grade_result(context)
    settings.GEMINI_API_KEY = "working-key"

    monkeypatch.setattr(
        "students.services.insights._generate_with_gemini",
        lambda signal: GeneratedInsight(
            title="AI title",
            message="AI body",
            category=signal.category,
            risk_band=signal.risk_band,
            delivery_status="DELIVERED",
            data={"summary": "generated"},
            generated_by="gemini",
        ),
    )

    def fail_fallback(signal):
        del signal
        error_message = "Rule-based fallback should not run."
        raise AssertionError(error_message)

    monkeypatch.setattr(
        "students.services.insights._build_rule_based_insight",
        fail_fallback,
    )

    payload = trigger_student_insight_demo(context["student"])

    notification = Notification.objects.get(id=payload["insight_id"])
    assert payload["created"] is True
    assert notification.title == "AI title"
    assert notification.message == "AI body"
    assert notification.data["generated_by"] == "gemini"
    assert notification.data["summary"] == "generated"


@pytest.mark.django_db
class TestTriggerInsightDemoAPI:
    @pytest.fixture
    def client(self):
        return APIClient()

    def test_trigger_insight_demo_returns_created_payload_from_gemini(
        self,
        client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
        settings,
    ):
        context = _build_student_context()
        _create_low_grade_result(context)
        settings.GEMINI_API_KEY = "working-key"
        client.force_authenticate(user=context["organization"].owner)

        monkeypatch.setattr(
            "students.services.insights._generate_with_gemini",
            lambda signal: GeneratedInsight(
                title="Gemini insight",
                message=(
                    "Insight generated and delivered through the parent "
                    "notification flow."
                ),
                category=signal.category,
                risk_band=signal.risk_band,
                delivery_status="DELIVERED",
                data={"audience": "parent"},
                generated_by="gemini",
            ),
        )

        response = client.post(
            f"/api/students/{context['student'].id}/trigger-insight-demo/",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] is True
        assert response.data["reused_existing"] is False
        assert response.data["category"] == "ACADEMICS"
        assert response.data["delivery_status"] == "DELIVERED"
        assert response.data["source_event_type"] == "ASSESSMENT_RESULT"

    def test_trigger_insight_demo_reuses_existing_notification(
        self,
        client: APIClient,
        monkeypatch: pytest.MonkeyPatch,
        settings,
    ):
        context = _build_student_context()
        _create_low_grade_result(context)
        settings.GEMINI_API_KEY = "working-key"
        client.force_authenticate(user=context["organization"].owner)

        monkeypatch.setattr(
            "students.services.insights._generate_with_gemini",
            lambda signal: GeneratedInsight(
                title="Gemini insight",
                message=(
                    "Insight generated and delivered through the parent "
                    "notification flow."
                ),
                category=signal.category,
                risk_band=signal.risk_band,
                delivery_status="DELIVERED",
                data={},
                generated_by="gemini",
            ),
        )

        endpoint = f"/api/students/{context['student'].id}/trigger-insight-demo/"
        first = client.post(endpoint)
        second = client.post(endpoint)

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data["created"] is True
        assert second.data["reused_existing"] is True
        assert first.data["insight_id"] == second.data["insight_id"]
        assert Notification.objects.count() == 1

    def test_trigger_insight_demo_returns_no_qualifying_signal(
        self,
        client: APIClient,
    ):
        context = _build_student_context()
        client.force_authenticate(user=context["organization"].owner)

        response = client.post(
            f"/api/students/{context['student'].id}/trigger-insight-demo/",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "created": False,
            "reason_code": NO_QUALIFYING_SIGNAL_REASON,
            "message": NO_QUALIFYING_SIGNAL_MESSAGE,
        }

    def test_trigger_insight_demo_rejects_inaccessible_student(
        self,
        client: APIClient,
    ):
        context = _build_student_context()
        other_user = StudentFactory().organization.owner
        client.force_authenticate(user=other_user)

        response = client.post(
            f"/api/students/{context['student'].id}/trigger-insight-demo/",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
