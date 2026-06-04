from __future__ import annotations

import json
from datetime import timedelta

import pytest
from academics.tests.factories import AcademicYearFactory
from academics.tests.factories import GradeFactory
from academics.tests.factories import SectionFactory
from academics.tests.factories import SubjectFactory
from accounts.tests.factories import UserFactory
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from django.utils import timezone
from django.utils.crypto import get_random_string
from messaging.models import ChatMessage
from messaging.models import ChatThread
from notifications.models import Notification
from student_insights.models import StudentInsight
from student_insights.provider import InsightGenerationResult
from student_insights.services import generate_parent_guidance
from student_insights.services import process_student_event
from student_insights.services import trigger_manual_student_insight
from students.tests.factories import ParentFactory
from students.tests.factories import ParentStudentLinkFactory
from students.tests.factories import StudentFactory
from teachers.models import Teacher
from teachers.models import TeacherSubjectAssignment

NOW = timezone.now
GEMINI_TIMEOUT_SECONDS = 5


def _build_assessment_result(student, **overrides):
    title = overrides.pop("title", "Quiz 1")
    task_type = overrides.pop("task_type", Assessment.TaskType.QUIZ)
    total_marks = overrides.pop("total_marks", "100")
    passing_marks = overrides.pop("passing_marks", "50")
    obtained_marks = overrides.pop("obtained_marks", "45")
    submission_status = overrides.pop(
        "submission_status",
        AssessmentResult.SubmissionStatus.GRADED,
    )
    if overrides:
        pytest.fail(f"Unexpected assessment result overrides: {sorted(overrides)}")

    user = student.parent_links.first().parent.user
    teacher = Teacher.objects.create(
        user=user.__class__.objects.create_user(
            email=f"teacher-{student.id}@example.com",
            password=get_random_string(16),
            role="TEACHER",
            name="Assigned Teacher",
        ),
        organization=student.organization,
        branch=student.branch,
        employee_id=f"EMP-{str(student.id)[:8]}",
        specialization="Mathematics",
    )
    academic_year = AcademicYearFactory(
        organization=student.organization,
        branch=student.branch,
        is_current=True,
    )
    grade = GradeFactory(organization=student.organization, branch=student.branch)
    section = SectionFactory(
        organization=student.organization,
        branch=student.branch,
        grade=grade,
        academic_year=academic_year,
        name="A",
    )
    student.current_section = section
    student.save(update_fields=["current_section", "updated_at"])
    subject = SubjectFactory(
        organization=student.organization,
        branch=student.branch,
        grade=grade,
        name="Mathematics",
    )
    assignment = TeacherSubjectAssignment.objects.create(
        teacher=teacher,
        organization=student.organization,
        subject=subject,
        section=section,
        academic_year=academic_year,
    )
    assessment = Assessment.objects.create(
        organization=student.organization,
        branch=student.branch,
        teacher_assignment=assignment,
        title=title,
        task_type=task_type,
        description="Assess concept mastery",
        total_marks=total_marks,
        passing_marks=passing_marks,
        due_date=NOW().date(),
        status=Assessment.Status.PUBLISHED,
    )
    return AssessmentResult.objects.create(
        organization=student.organization,
        assessment=assessment,
        student=student,
        obtained_marks=obtained_marks,
        submission_status=submission_status,
        feedback="Needs support",
    )


@pytest.mark.django_db
class TestStudentInsightServices:
    def test_generate_parent_guidance_uses_gemini_when_response_is_valid(
        self,
        monkeypatch,
        settings,
    ):
        settings.STUDENT_INSIGHTS_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = "test-key"
        settings.GEMINI_MODEL = "gemini-test"
        settings.GEMINI_TIMEOUT_SECONDS = GEMINI_TIMEOUT_SECONDS

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "title": "Academic support update",
                                                "summary": (
                                                    "Recent academic performance "
                                                    "suggests extra support may help."
                                                ),
                                                "recommended_actions": [
                                                    (
                                                        "Review the latest schoolwork "
                                                        "together."
                                                    ),
                                                    (
                                                        "Contact the teacher if help "
                                                        "is needed."
                                                    ),
                                                ],
                                                "confidence_label": "GEMINI",
                                            },
                                        ),
                                    },
                                ],
                            },
                        },
                    ],
                }

        def fake_post(url, *, params, json, timeout):
            assert "gemini-test:generateContent" in url
            assert params == {"key": "test-key"}
            assert timeout == GEMINI_TIMEOUT_SECONDS
            assert "Payload:" in json["contents"][0]["parts"][0]["text"]
            return FakeResponse()

        monkeypatch.setattr("student_insights.provider.httpx.post", fake_post)

        generated, safety_status, notes = generate_parent_guidance(
            {
                "category": "ACADEMICS",
                "risk_band": "LOW",
                "concern_summary": (
                    "Recent academic performance suggests extra support may help."
                ),
                "tags": ["academics"],
                "fallback_title": "Academic support update",
                "suggested_actions": [],
            },
        )

        assert safety_status == StudentInsight.SafetyStatus.APPROVED
        assert notes == []
        assert generated["confidence_label"] == "GEMINI"
        assert "rule based" not in generated["summary"].lower()

    def test_generate_parent_guidance_falls_back_on_provider_error(
        self,
        monkeypatch,
        settings,
    ):
        settings.STUDENT_INSIGHTS_PROVIDER = "gemini"
        settings.GEMINI_API_KEY = "test-key"

        def fake_post(*args, **kwargs):
            del args, kwargs
            msg = "provider unavailable"
            raise RuntimeError(msg)

        monkeypatch.setattr("student_insights.provider.httpx.post", fake_post)

        generated, safety_status, notes = generate_parent_guidance(
            {
                "category": "ACADEMICS",
                "risk_band": "LOW",
                "concern_summary": (
                    "Recent performance suggests additional support may help."
                ),
                "tags": ["academics"],
                "fallback_title": "Academic support update",
                "suggested_actions": [],
            },
        )

        assert safety_status == StudentInsight.SafetyStatus.FALLBACK
        assert notes == ["provider_error"]
        assert generated["confidence_label"] == "FALLBACK"

    def test_generate_parent_guidance_falls_back_on_policy_violation(self, monkeypatch):
        class UnsafeProvider:
            def generate(self, payload):
                del payload
                return InsightGenerationResult(
                    title="Medical diagnosis",
                    summary="This requires medical advice immediately.",
                    recommended_actions=["Punish the child.", "Call a lawyer."],
                    confidence_label="MOCK",
                )

        monkeypatch.setattr("student_insights.services._get_provider", UnsafeProvider)

        generated, safety_status, notes = generate_parent_guidance(
            {
                "category": "ACADEMICS",
                "risk_band": "LOW",
                "concern_summary": (
                    "Recent performance suggests additional support may help."
                ),
                "tags": ["academics"],
                "fallback_title": "Academic support update",
                "suggested_actions": [],
            },
        )

        assert safety_status == StudentInsight.SafetyStatus.FALLBACK
        assert "forbidden_term" in notes
        assert generated["confidence_label"] == "FALLBACK"

    def test_assessment_result_creates_insight_and_parent_notification(self):
        student = StudentFactory()
        parent = ParentFactory(
            organizations=[student.organization],
            branches=[student.branch],
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        result = _build_assessment_result(student)

        insight = process_student_event(
            source_event_type=StudentInsight.SourceEventType.ASSESSMENT_RESULT,
            source_model="assessments.AssessmentResult",
            source_id=str(result.id),
        )

        assert insight is not None
        assert insight.category == StudentInsight.Category.ACADEMICS
        assert insight.delivery_status in {
            StudentInsight.DeliveryStatus.DELIVERED,
            StudentInsight.DeliveryStatus.SUPPRESSED,
        }
        notification = Notification.objects.filter(
            recipient=parent.user,
            data__category="insight",
            data__insight_id=str(insight.id),
        ).first()
        assert notification is not None

    def test_chat_message_dedupes_same_concern_within_cooldown(self, settings):
        settings.STUDENT_INSIGHTS_COOLDOWN_HOURS = 24
        student = StudentFactory()
        parent = ParentFactory(
            organizations=[student.organization],
            branches=[student.branch],
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        thread = ChatThread.objects.create(
            student=student,
            parent=parent,
            teacher=Teacher.objects.create(
                user=parent.user.__class__.objects.create_user(
                    email=f"teacher2-{student.id}@example.com",
                    password=get_random_string(16),
                    role="TEACHER",
                    name="Concern Teacher",
                ),
                organization=student.organization,
                branch=student.branch,
                employee_id=f"EMP2-{str(student.id)[:8]}",
                specialization="English",
            ),
            organization=student.organization,
            branch=student.branch,
        )
        first = ChatMessage.objects.create(
            thread=thread,
            sender=thread.teacher.user,
            text="Your child is struggling with homework and missed class.",
        )
        second = ChatMessage.objects.create(
            thread=thread,
            sender=thread.teacher.user,
            text="Still struggling with homework and missed class.",
        )

        first_insight = process_student_event(
            source_event_type=StudentInsight.SourceEventType.CHAT_MESSAGE,
            source_model="messaging.ChatMessage",
            source_id=str(first.id),
        )
        second_insight = process_student_event(
            source_event_type=StudentInsight.SourceEventType.CHAT_MESSAGE,
            source_model="messaging.ChatMessage",
            source_id=str(second.id),
        )

        assert first_insight is not None
        assert second_insight is not None
        assert first_insight.id == second_insight.id

    def test_manual_trigger_returns_no_signal_when_student_has_no_qualifying_data(self):
        student = StudentFactory()
        triggered_by = UserFactory(role="TEACHER")

        result = trigger_manual_student_insight(
            student_id=str(student.id),
            triggered_by_user=triggered_by,
        )

        assert result.created is False
        assert result.reason_code == "NO_QUALIFYING_SIGNAL"
        assert result.insight is None

    def test_manual_trigger_prefers_academics_over_attendance(self):
        student = StudentFactory()
        parent = ParentFactory(
            organizations=[student.organization],
            branches=[student.branch],
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        triggered_by = UserFactory(role="TEACHER")
        result = _build_assessment_result(student, obtained_marks="30")
        Attendance.objects.create(
            organization=student.organization,
            branch=student.branch,
            academic_year=result.assessment.academic_year,
            section=result.assessment.section,
            student=student,
            recorded_by=triggered_by,
            date=NOW().date(),
            status=Attendance.Status.ABSENT,
        )
        Attendance.objects.create(
            organization=student.organization,
            branch=student.branch,
            academic_year=result.assessment.academic_year,
            section=result.assessment.section,
            student=student,
            recorded_by=triggered_by,
            date=NOW().date() - timedelta(days=1),
            status=Attendance.Status.ABSENT,
        )
        Attendance.objects.create(
            organization=student.organization,
            branch=student.branch,
            academic_year=result.assessment.academic_year,
            section=result.assessment.section,
            student=student,
            recorded_by=triggered_by,
            date=NOW().date() - timedelta(days=2),
            status=Attendance.Status.ABSENT,
        )

        manual = trigger_manual_student_insight(
            student_id=str(student.id),
            triggered_by_user=triggered_by,
        )

        assert manual.created is True
        assert manual.insight is not None
        assert manual.insight.category == StudentInsight.Category.ACADEMICS

    def test_manual_trigger_reuses_existing_recent_insight(self):
        student = StudentFactory()
        parent = ParentFactory(
            organizations=[student.organization],
            branches=[student.branch],
        )
        ParentStudentLinkFactory(student=student, parent=parent)
        triggered_by = UserFactory(role="TEACHER")
        _build_assessment_result(student, obtained_marks="30")

        first = trigger_manual_student_insight(
            student_id=str(student.id),
            triggered_by_user=triggered_by,
        )
        second = trigger_manual_student_insight(
            student_id=str(student.id),
            triggered_by_user=triggered_by,
        )

        assert first.created is True
        assert second.created is True
        assert first.insight is not None
        assert second.insight is not None
        assert second.reused_existing is True
        assert second.insight.id == first.insight.id
        assert "demo" not in second.message.lower()
