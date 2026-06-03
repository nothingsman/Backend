from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any

from assessments.models import Assessment
from assessments.models import AssessmentResult
from assessments.models import HomeworkConfirmation
from attendance.models import Attendance
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.db.models import Q
from messaging.models import ChatMessage
from notifications.models import Notification
from notifications.services import create_notification_once
from students.models import ParentStudentLink
from students.models import Student

NO_QUALIFYING_SIGNAL_REASON = "NO_QUALIFYING_SIGNAL"
NO_QUALIFYING_SIGNAL_MESSAGE = (
    "No current qualifying grade, attendance, homework, or message signal was found "
    "for this student."
)
NO_PARENT_RECIPIENT_REASON = "NO_PARENT_RECIPIENT"
NO_PARENT_RECIPIENT_MESSAGE = (
    "No active parent recipient is linked to this student, so no insight could be "
    "delivered."
)

_CATEGORY_VALUES = {"ACADEMICS", "HOMEWORK", "ATTENDANCE", "COMMUNICATION"}
_RISK_BAND_VALUES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_DELIVERY_STATUS = "DELIVERED"
_RISK_THRESHOLD_CRITICAL = 40
_RISK_THRESHOLD_HIGH = 60
_RISK_THRESHOLD_MEDIUM = 75

_INSIGHT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "title",
        "message",
        "category",
        "risk_band",
        "delivery_status",
        "data",
    ],
    "properties": {
        "title": {"type": "string"},
        "message": {"type": "string"},
        "category": {"type": "string", "enum": sorted(_CATEGORY_VALUES)},
        "risk_band": {"type": "string", "enum": sorted(_RISK_BAND_VALUES)},
        "delivery_status": {"type": "string", "enum": [_DELIVERY_STATUS]},
        "data": {"type": "object"},
    },
    "additionalProperties": False,
}


class GeminiGenerationError(RuntimeError):
    pass


def _raise_gemini_error(message: str) -> None:
    raise GeminiGenerationError(message)


@dataclass(frozen=True)
class InsightSignal:
    notifiable: Any
    source_event_type: str
    source_model: str
    source_id: str
    category: str
    risk_band: str
    prompt_context: dict[str, Any]


@dataclass(frozen=True)
class GeneratedInsight:
    title: str
    message: str
    category: str
    risk_band: str
    delivery_status: str
    data: dict[str, Any]
    generated_by: str


def trigger_student_insight_demo(student: Student) -> dict[str, Any]:
    signal = select_latest_qualifying_signal(student)
    if signal is None:
        return {
            "created": False,
            "reason_code": NO_QUALIFYING_SIGNAL_REASON,
            "message": NO_QUALIFYING_SIGNAL_MESSAGE,
        }

    recipient = _get_parent_recipient(student)
    if recipient is None:
        return {
            "created": False,
            "reason_code": NO_PARENT_RECIPIENT_REASON,
            "message": NO_PARENT_RECIPIENT_MESSAGE,
            "source_event_type": signal.source_event_type,
            "source_model": signal.source_model,
            "source_id": signal.source_id,
        }

    event_key = _build_event_key(student=student, signal=signal)
    existing = _get_existing_notification(
        recipient=recipient,
        notifiable=signal.notifiable,
        event_key=event_key,
    )
    if existing is not None:
        return _build_response_from_notification(
            notification=existing,
            signal=signal,
            reused_existing=True,
        )

    generated = generate_insight_content(signal)
    notification_data = {
        "category": generated.category,
        "risk_band": generated.risk_band,
        "delivery_status": generated.delivery_status,
        "source_event_type": signal.source_event_type,
        "source_model": signal.source_model,
        "source_id": signal.source_id,
        "student_id": str(student.id),
        "branch_id": str(student.branch_id),
        "organization_id": str(student.organization_id),
        "generated_by": generated.generated_by,
        "insight_type": "student_insight_demo",
        **generated.data,
    }
    notification = create_notification_once(
        recipient=recipient,
        notifiable=signal.notifiable,
        title=generated.title,
        message=generated.message,
        event_key=event_key,
        data=notification_data,
    )
    return _build_response_from_notification(
        notification=notification,
        signal=signal,
        reused_existing=False,
    )


def select_latest_qualifying_signal(student: Student) -> InsightSignal | None:
    selectors = (
        _get_low_grade_signal,
        _get_homework_signal,
        _get_attendance_signal,
        _get_chat_signal,
    )
    for selector in selectors:
        signal = selector(student)
        if signal is not None:
            return signal
    return None


def generate_insight_content(signal: InsightSignal) -> GeneratedInsight:
    try:
        return _generate_with_gemini(signal)
    except GeminiGenerationError:
        return _build_rule_based_insight(signal)


def _get_low_grade_signal(student: Student) -> InsightSignal | None:
    result = (
        AssessmentResult.objects.select_related(
            "assessment__teacher_assignment__teacher__user",
            "assessment__teacher_assignment__subject",
            "assessment__teacher_assignment__section",
            "student",
        )
        .filter(
            student=student,
            submission_status=AssessmentResult.SubmissionStatus.GRADED,
            obtained_marks__isnull=False,
            assessment__passing_marks__isnull=False,
            obtained_marks__lt=F("assessment__passing_marks"),
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if result is None:
        return None

    assessment = result.assessment
    percentage = result.percentage
    return InsightSignal(
        notifiable=result,
        source_event_type="ASSESSMENT_RESULT",
        source_model="assessments.AssessmentResult",
        source_id=str(result.id),
        category="ACADEMICS",
        risk_band=_risk_band_from_percentage(percentage),
        prompt_context={
            "student_name": f"{student.first_name} {student.last_name}",
            "student_roll_no": student.roll_no,
            "assessment_title": assessment.title,
            "subject_name": assessment.subject.name,
            "section_name": assessment.section.name,
            "teacher_name": assessment.teacher.user.name,
            "obtained_marks": str(result.obtained_marks),
            "passing_marks": str(assessment.passing_marks),
            "total_marks": str(assessment.total_marks),
            "percentage": percentage,
            "qualifying_signal": "low_grade",
        },
    )


def _get_homework_signal(student: Student) -> InsightSignal | None:
    result = (
        AssessmentResult.objects.select_related(
            "assessment__teacher_assignment__teacher__user",
            "assessment__teacher_assignment__subject",
            "assessment__teacher_assignment__section",
            "student",
        )
        .filter(
            student=student,
            assessment__task_type=Assessment.TaskType.HOMEWORK,
        )
        .filter(
            Q(
                submission_status__in=[
                    AssessmentResult.SubmissionStatus.LATE,
                    AssessmentResult.SubmissionStatus.MISSING,
                ],
            )
            | Q(parent_confirmed=False),
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if result is not None:
        assessment = result.assessment
        return InsightSignal(
            notifiable=result,
            source_event_type="HOMEWORK_STATUS",
            source_model="assessments.AssessmentResult",
            source_id=str(result.id),
            category="HOMEWORK",
            risk_band="MEDIUM"
            if result.submission_status == AssessmentResult.SubmissionStatus.LATE
            else "HIGH",
            prompt_context={
                "student_name": f"{student.first_name} {student.last_name}",
                "student_roll_no": student.roll_no,
                "assessment_title": assessment.title,
                "subject_name": assessment.subject.name,
                "section_name": assessment.section.name,
                "teacher_name": assessment.teacher.user.name,
                "submission_status": result.submission_status,
                "parent_confirmed": result.parent_confirmed,
                "qualifying_signal": "homework_result",
            },
        )

    confirmation = (
        HomeworkConfirmation.objects.select_related(
            "assessment__teacher_assignment__teacher__user",
            "assessment__teacher_assignment__subject",
            "section",
            "student",
        )
        .filter(
            student=student,
            is_confirmed=False,
        )
        .order_by("-updated_at", "-created_at")
        .first()
    )
    if confirmation is None:
        return None

    assessment = confirmation.assessment
    return InsightSignal(
        notifiable=confirmation,
        source_event_type="HOMEWORK_CONFIRMATION",
        source_model="assessments.HomeworkConfirmation",
        source_id=str(confirmation.id),
        category="HOMEWORK",
        risk_band="MEDIUM",
        prompt_context={
            "student_name": f"{student.first_name} {student.last_name}",
            "student_roll_no": student.roll_no,
            "assessment_title": assessment.title,
            "subject_name": assessment.subject.name,
            "section_name": confirmation.section.name,
            "teacher_name": assessment.teacher.user.name,
            "is_confirmed": confirmation.is_confirmed,
            "qualifying_signal": "homework_confirmation",
        },
    )


def _get_attendance_signal(student: Student) -> InsightSignal | None:
    attendance = (
        Attendance.objects.select_related("reason", "section", "student")
        .filter(
            student=student,
            status__in=[Attendance.Status.ABSENT, Attendance.Status.LATE],
        )
        .filter(Q(reason__isnull=True) | Q(reason__parent_confirmed=False))
        .order_by("-date", "-updated_at", "-created_at")
        .first()
    )
    if attendance is None:
        return None

    return InsightSignal(
        notifiable=attendance,
        source_event_type="ATTENDANCE_STATUS",
        source_model="attendance.Attendance",
        source_id=str(attendance.id),
        category="ATTENDANCE",
        risk_band="HIGH" if attendance.status == Attendance.Status.ABSENT else "MEDIUM",
        prompt_context={
            "student_name": f"{student.first_name} {student.last_name}",
            "student_roll_no": student.roll_no,
            "attendance_date": attendance.date.isoformat(),
            "attendance_status": attendance.status,
            "section_name": attendance.section.name,
            "remarks": attendance.remarks,
            "qualifying_signal": "attendance_status",
        },
    )


def _get_chat_signal(student: Student) -> InsightSignal | None:
    message = (
        ChatMessage.objects.select_related(
            "thread__teacher__user",
            "thread__parent__user",
            "thread__student",
            "sender",
        )
        .filter(
            thread__student=student,
            sender__role="TEACHER",
        )
        .order_by("-created_at")
        .first()
    )
    if message is None:
        return None

    teacher_name = message.thread.teacher.user.name or "Teacher"
    return InsightSignal(
        notifiable=message,
        source_event_type="CHAT_ACTIVITY",
        source_model="messaging.ChatMessage",
        source_id=str(message.id),
        category="COMMUNICATION",
        risk_band="LOW",
        prompt_context={
            "student_name": f"{student.first_name} {student.last_name}",
            "student_roll_no": student.roll_no,
            "teacher_name": teacher_name,
            "message_text": message.text,
            "qualifying_signal": "teacher_message",
        },
    )


def _generate_with_gemini(signal: InsightSignal) -> GeneratedInsight:
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        error_message = "Missing GEMINI_API_KEY."
        _raise_gemini_error(error_message)

    try:
        genai = importlib.import_module("google.genai")
        types = importlib.import_module("google.genai.types")
    except ImportError as exc:  # pragma: no cover - exercised via fallback behavior
        error_message = "google-genai is not installed."
        raise GeminiGenerationError(error_message) from exc

    client = genai.Client(api_key=api_key)
    prompt = _build_gemini_prompt(signal)
    try:
        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_INSIGHT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_INSIGHT_RESPONSE_SCHEMA,
                temperature=0.2,
            ),
        )
    except Exception as exc:
        error_message = "Gemini request failed."
        raise GeminiGenerationError(error_message) from exc

    payload = getattr(response, "parsed", None)
    if payload is None:
        raw_text = getattr(response, "text", "") or ""
        if not raw_text:
            error_message = "Gemini returned an empty response."
            _raise_gemini_error(error_message)
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            error_message = "Gemini did not return valid JSON."
            raise GeminiGenerationError(error_message) from exc

    return _validate_generated_payload(payload, generated_by="gemini")


def _build_rule_based_insight(signal: InsightSignal) -> GeneratedInsight:
    ctx = signal.prompt_context
    student_name = ctx["student_name"]
    if signal.source_event_type == "ASSESSMENT_RESULT":
        title = f"Academic insight for {student_name}"
        message = (
            f"{student_name} scored {ctx['obtained_marks']}/{ctx['total_marks']} in "
            f"{ctx['subject_name']} on {ctx['assessment_title']}. "
            "A parent check-in is recommended."
        )
    elif signal.source_event_type in {"HOMEWORK_STATUS", "HOMEWORK_CONFIRMATION"}:
        title = f"Homework insight for {student_name}"
        message = (
            f"{student_name} needs parent follow-up for homework in "
            f"{ctx['subject_name']}. "
            f"Please review {ctx['assessment_title']} with the family."
        )
    elif signal.source_event_type == "ATTENDANCE_STATUS":
        message = (
            f"{student_name} was marked {ctx['attendance_status'].lower()} on "
            f"{ctx['attendance_date']}. A parent explanation or follow-up is needed."
        )
        title = f"Attendance insight for {student_name}"
    else:
        title = f"Communication insight for {student_name}"
        message = (
            f"{ctx['teacher_name']} recently sent a message about {student_name}. "
            "A parent follow-up is recommended."
        )

    return GeneratedInsight(
        title=title,
        message=message,
        category=signal.category,
        risk_band=signal.risk_band,
        delivery_status=_DELIVERY_STATUS,
        data={},
        generated_by="rule_based",
    )


def _validate_generated_payload(
    payload: Any,
    *,
    generated_by: str,
) -> GeneratedInsight:
    if not isinstance(payload, dict):
        error_message = "Gemini payload must be an object."
        _raise_gemini_error(error_message)

    title = payload.get("title")
    message = payload.get("message")
    category = payload.get("category")
    risk_band = payload.get("risk_band")
    delivery_status = payload.get("delivery_status")
    data = payload.get("data")

    if not isinstance(title, str) or not title.strip():
        error_message = "Gemini title is invalid."
        _raise_gemini_error(error_message)
    if not isinstance(message, str) or not message.strip():
        error_message = "Gemini message is invalid."
        _raise_gemini_error(error_message)
    if category not in _CATEGORY_VALUES:
        error_message = "Gemini category is invalid."
        _raise_gemini_error(error_message)
    if risk_band not in _RISK_BAND_VALUES:
        error_message = "Gemini risk band is invalid."
        _raise_gemini_error(error_message)
    if delivery_status != _DELIVERY_STATUS:
        error_message = "Gemini delivery status is invalid."
        _raise_gemini_error(error_message)
    if not isinstance(data, dict):
        error_message = "Gemini data payload is invalid."
        _raise_gemini_error(error_message)

    return GeneratedInsight(
        title=title.strip(),
        message=message.strip(),
        category=category,
        risk_band=risk_band,
        delivery_status=delivery_status,
        data=data,
        generated_by=generated_by,
    )


def _build_gemini_prompt(signal: InsightSignal) -> str:
    signal_context = json.dumps(
        signal.prompt_context,
        default=str,
        sort_keys=True,
    )
    return (
        "You are generating a concise parent-facing student insight notification. "
        "Return JSON only and match the provided schema exactly.\n"
        f"Preferred category: {signal.category}\n"
        f"Preferred risk band: {signal.risk_band}\n"
        f"Delivery status must be {_DELIVERY_STATUS}.\n"
        "Tone: specific, calm, actionable, and suitable for a school parent "
        "notification.\n"
        f"Signal context: {signal_context}"
    )


def _build_event_key(*, student: Student, signal: InsightSignal) -> str:
    return (
        "student.insight_demo:"
        f"{student.id}:{signal.source_event_type}:{signal.source_id}"
    )


def _get_parent_recipient(student: Student):
    primary_link = (
        ParentStudentLink.objects.select_related("parent__user")
        .filter(student=student, parent__is_active=True)
        .order_by("-is_primary_contact", "-created_at")
        .first()
    )
    return primary_link.parent.user if primary_link is not None else None


def _get_existing_notification(*, recipient, notifiable, event_key: str):
    notifiable_type = ContentType.objects.get_for_model(
        notifiable,
        for_concrete_model=False,
    )
    return (
        Notification.objects.filter(
            recipient=recipient,
            notifiable_type=notifiable_type,
            notifiable_id=str(notifiable.pk),
            data__event_key=event_key,
        )
        .order_by("-created_at")
        .first()
    )


def _build_response_from_notification(
    *,
    notification: Notification,
    signal: InsightSignal,
    reused_existing: bool,
) -> dict[str, Any]:
    return {
        "created": True,
        "reused_existing": reused_existing,
        "insight_id": str(notification.id),
        "category": notification.data.get("category", signal.category),
        "risk_band": notification.data.get("risk_band", signal.risk_band),
        "delivery_status": notification.data.get("delivery_status", _DELIVERY_STATUS),
        "message": notification.message,
        "source_event_type": signal.source_event_type,
        "source_model": signal.source_model,
        "source_id": signal.source_id,
    }


def _risk_band_from_percentage(percentage: float | None) -> str:
    if percentage is None:
        return "MEDIUM"
    if percentage < _RISK_THRESHOLD_CRITICAL:
        return "CRITICAL"
    if percentage < _RISK_THRESHOLD_HIGH:
        return "HIGH"
    if percentage < _RISK_THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"
