from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any

from analytics.models import InterventionLog
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceReason
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from messaging.models import ChatMessage
from notifications.services import create_notification_once
from student_insights.models import StudentInsight
from student_insights.provider import GeminiInsightGenerationProvider
from student_insights.provider import InsightGenerationProvider
from student_insights.provider import RuleBasedInsightGenerationProvider
from students.models import ParentStudentLink
from students.models import Student

if TYPE_CHECKING:
    from decimal import Decimal

    from accounts.models import User

FORBIDDEN_OUTPUT_TERMS = (
    "diagnosis",
    "medical advice",
    "legal advice",
    "punish",
    "disorder",
    "rule based",
    "rule-based",
    "demo",
)
CHAT_CONCERN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "attendance": ("absent", "absence", "late", "transport", "missed class"),
    "academics": ("struggling", "grade", "failed", "homework", "exam", "quiz"),
    "wellbeing": ("stress", "bully", "unsafe", "hurt", "anxious"),
}
MAX_TITLE_LENGTH = 255
MAX_SUMMARY_LENGTH = 280
MIN_ACTION_COUNT = 2
MAX_ACTION_COUNT = 3
MAX_ACTION_LENGTH = 120
MEDIUM_TAG_MATCH_COUNT = 2
DECLINE_SAMPLE_SIZE = 3
DECLINE_THRESHOLD = 15
HOMEWORK_ALERT_COUNT = 2
HOMEWORK_HIGH_RISK_COUNT = 3
LOW_SCORE_THRESHOLD = 60
MEDIUM_SCORE_THRESHOLD = 50
HIGH_RISK_SCORE_THRESHOLD = 35
ATTENDANCE_ABSENCE_ALERT_COUNT = 3
ATTENDANCE_ABSENCE_HIGH_RISK_COUNT = 4
ATTENDANCE_LATE_ALERT_COUNT = 4


@dataclass(slots=True)
class InsightDecision:
    should_create: bool
    category: str = ""
    risk_band: str = ""
    title: str = ""
    concern_summary: str = ""
    evidence: dict[str, Any] | None = None
    dedupe_key: str = ""
    suggested_actions: list[str] | None = None
    safety_notes: list[str] | None = None


@dataclass(slots=True)
class InsightProcessingResult:
    insight: StudentInsight | None
    reused_existing: bool = False


@dataclass(slots=True)
class ManualInsightTriggerResult:
    created: bool
    insight: StudentInsight | None = None
    reused_existing: bool = False
    reason_code: str = ""
    message: str = ""
    source_event_type: str = ""
    source_model: str = ""
    source_id: str = ""


@dataclass(slots=True, frozen=True)
class EventContext:
    source_event_type: str
    source_model: str
    source_id: str


def _get_provider() -> InsightGenerationProvider:
    provider_name = getattr(settings, "STUDENT_INSIGHTS_PROVIDER", "mock").lower()
    if provider_name == "gemini" and settings.GEMINI_API_KEY:
        return GeminiInsightGenerationProvider(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        )
    return RuleBasedInsightGenerationProvider()


def _coerce_decimal(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _get_student_parents(student: Student):
    return ParentStudentLink.objects.select_related("parent__user").filter(
        student=student,
        parent__is_active=True,
    )


def _model_allowed_output(
    result: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    title = str(result.get("title", "")).strip()
    summary = str(result.get("summary", "")).strip()
    actions = result.get("recommended_actions")

    if not title or len(title) > MAX_TITLE_LENGTH:
        notes.append("invalid_title")
    if not summary or len(summary) > MAX_SUMMARY_LENGTH:
        notes.append("invalid_summary")
    if (
        not isinstance(actions, list)
        or len(actions) < MIN_ACTION_COUNT
        or len(actions) > MAX_ACTION_COUNT
    ):
        notes.append("invalid_actions")
    else:
        for action in actions:
            if (
                not isinstance(action, str)
                or len(action.strip()) == 0
                or len(action) > MAX_ACTION_LENGTH
            ):
                notes.append("invalid_action_entry")
                break

    output_text = " ".join(
        [
            title.lower(),
            summary.lower(),
            " ".join(str(action).lower() for action in actions or []),
        ],
    )
    if any(term in output_text for term in FORBIDDEN_OUTPUT_TERMS):
        notes.append("forbidden_term")

    expected_keywords = [
        str(payload.get("category", "")).lower(),
        *[str(tag).lower() for tag in payload.get("tags", [])],
    ]

    normalized_keywords: list[str] = []
    for keyword in expected_keywords:
        cleaned = keyword.strip()
        if not cleaned:
            continue
        normalized_keywords.append(cleaned)
        normalized_keywords.append(cleaned.replace("_", " "))
        if cleaned.endswith("s") and len(cleaned) > 1:
            normalized_keywords.append(cleaned[:-1])

    if expected_keywords and not any(
        keyword and keyword in output_text for keyword in normalized_keywords
    ):
        notes.append("missing_expected_context")

    return (len(notes) == 0, notes)


def _build_fallback_guidance(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(payload.get("fallback_title", "School update for your child"))[
            :MAX_TITLE_LENGTH
        ],
        "summary": str(
            payload.get("concern_summary", "A school-related concern was detected."),
        )[:MAX_SUMMARY_LENGTH],
        "recommended_actions": [
            "Talk with your child about this update today.",
            "Review the recent school record with them.",
            "Contact the teacher if you need more context.",
        ],
        "confidence_label": "FALLBACK",
    }


def _severity_rank(risk_band: str) -> int:
    return {
        StudentInsight.RiskBand.LOW: 1,
        StudentInsight.RiskBand.MEDIUM: 2,
        StudentInsight.RiskBand.HIGH: 3,
    }[risk_band]


def _recent_duplicate(
    decision: InsightDecision,
    student: Student,
) -> StudentInsight | None:
    cooldown_hours = getattr(settings, "STUDENT_INSIGHTS_COOLDOWN_HOURS", 24)
    since = timezone.now() - timedelta(hours=cooldown_hours)
    return (
        StudentInsight.objects.filter(
            student=student,
            category=decision.category,
            dedupe_key=decision.dedupe_key,
            created_at__gte=since,
        )
        .order_by("-created_at")
        .first()
    )


def build_student_signal_snapshot(
    student_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    student = Student.objects.select_related(
        "organization",
        "branch",
        "current_section__grade",
    ).get(id=student_id)
    now = timezone.localdate()
    recent_results = list(
        AssessmentResult.objects.select_related(
            "assessment__teacher_assignment__subject",
            "assessment__teacher_assignment__section",
        )
        .filter(student=student, obtained_marks__isnull=False)
        .order_by("-created_at")[:5],
    )
    attendance_window = Attendance.objects.filter(
        student=student,
        date__gte=now - timedelta(days=30),
    )
    recent_absences = attendance_window.filter(status=Attendance.Status.ABSENT).count()
    recent_lates = attendance_window.filter(status=Attendance.Status.LATE).count()
    homework_missing = (
        AssessmentResult.objects.filter(
            student=student,
            assessment__task_type=Assessment.TaskType.HOMEWORK,
            assessment__due_date__lte=now,
        )
        .filter(
            Q(submission_status=AssessmentResult.SubmissionStatus.MISSING)
            | Q(submission_status=AssessmentResult.SubmissionStatus.LATE)
            | Q(submission_status=AssessmentResult.SubmissionStatus.PENDING),
        )
        .count()
    )

    return {
        "student_id": str(student.id),
        "organization_id": str(student.organization_id),
        "branch_id": str(student.branch_id),
        "section_name": student.current_section.name
        if student.current_section_id
        else "",
        "grade_name": (
            student.current_section.grade.name if student.current_section_id else ""
        ),
        "recent_results": [
            {
                "assessment_id": str(result.assessment_id),
                "task_type": result.assessment.task_type,
                "subject_name": result.assessment.subject.name,
                "percentage": result.percentage,
                "is_below_passing": result.is_below_passing,
                "submission_status": result.submission_status,
            }
            for result in recent_results
        ],
        "recent_absences": recent_absences,
        "recent_lates": recent_lates,
        "homework_missing": homework_missing,
        "event": event,
    }


def _subject_decline_percentages(student: Student, subject_id: str) -> list[float]:
    results = (
        AssessmentResult.objects.select_related("assessment")
        .filter(
            student=student,
            assessment__teacher_assignment__subject_id=subject_id,
            obtained_marks__isnull=False,
        )
        .order_by("-created_at")[:3]
    )
    return [
        percentage
        for result in results
        if (percentage := result.percentage) is not None
    ]


def _classify_chat_message(message: ChatMessage) -> tuple[str | None, list[str]]:
    text = (message.text or "").lower()
    matched_tags = [
        tag
        for tag, keywords in CHAT_CONCERN_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    if not matched_tags:
        return None, []
    if "wellbeing" in matched_tags:
        return StudentInsight.RiskBand.HIGH, matched_tags
    if len(matched_tags) >= MEDIUM_TAG_MATCH_COUNT:
        return StudentInsight.RiskBand.MEDIUM, matched_tags
    return StudentInsight.RiskBand.LOW, matched_tags


def _score_assessment_result(
    *,
    snapshot: dict[str, Any],
    student: Student,
    source_id: str,
) -> InsightDecision:
    result = AssessmentResult.objects.select_related(
        "assessment__teacher_assignment__subject",
    ).get(id=source_id)
    percentage = result.percentage or 0.0
    decline = _subject_decline_percentages(
        student,
        str(result.assessment.teacher_assignment.subject_id),
    )
    declining = (
        len(decline) >= DECLINE_SAMPLE_SIZE
        and decline[0] < decline[1] < decline[2]
        and (decline[2] - decline[0]) >= DECLINE_THRESHOLD
    )
    is_homework = result.assessment.task_type == Assessment.TaskType.HOMEWORK
    has_homework_signal = (
        result.submission_status
        in {
            AssessmentResult.SubmissionStatus.MISSING,
            AssessmentResult.SubmissionStatus.LATE,
            AssessmentResult.SubmissionStatus.PENDING,
        }
        or snapshot["homework_missing"] >= HOMEWORK_ALERT_COUNT
    )
    is_homework_alert = is_homework and has_homework_signal
    if is_homework_alert:
        high_risk_homework = snapshot["homework_missing"] >= HOMEWORK_HIGH_RISK_COUNT
        risk_band = (
            StudentInsight.RiskBand.HIGH
            if high_risk_homework
            else StudentInsight.RiskBand.MEDIUM
        )
        return InsightDecision(
            should_create=True,
            category=StudentInsight.Category.ENGAGEMENT,
            risk_band=risk_band,
            title="Homework follow-up needed",
            concern_summary="Recent homework records show missing or late completion.",
            evidence={
                "homework_missing": snapshot["homework_missing"],
                "submission_status": result.submission_status,
                "task_type": result.assessment.task_type,
            },
            dedupe_key=f"engagement:homework:{student.id}:{high_risk_homework}",
            suggested_actions=[
                "Review incomplete homework with your child.",
                "Set a study time for the next school days.",
                "Contact the teacher if support is needed.",
            ],
        )

    needs_academic_follow_up = (
        result.is_below_passing or declining or percentage <= LOW_SCORE_THRESHOLD
    )
    if not needs_academic_follow_up:
        return InsightDecision(should_create=False)

    if percentage <= HIGH_RISK_SCORE_THRESHOLD:
        risk_band = StudentInsight.RiskBand.HIGH
    elif percentage <= MEDIUM_SCORE_THRESHOLD or declining:
        risk_band = StudentInsight.RiskBand.MEDIUM
    else:
        risk_band = StudentInsight.RiskBand.LOW
    return InsightDecision(
        should_create=True,
        category=StudentInsight.Category.ACADEMICS,
        risk_band=risk_band,
        title="Academic progress needs attention",
        concern_summary=(
            "Recent assessment performance suggests your child may need extra "
            "academic support."
        ),
        evidence={
            "percentage": percentage,
            "is_below_passing": result.is_below_passing,
            "declining_scores": declining,
            "subject_name": result.assessment.subject.name,
            "task_type": result.assessment.task_type,
        },
        dedupe_key=(
            "academics:"
            f"{result.assessment.teacher_assignment.subject_id}:"
            f"{int(percentage // 10)}"
        ),
        suggested_actions=[
            "Ask your child which topic felt difficult.",
            "Review the latest graded work together.",
            "Contact the teacher about targeted support.",
        ],
    )


def _score_attendance(snapshot: dict[str, Any], student: Student) -> InsightDecision:
    has_attendance_alert = (
        snapshot["recent_absences"] >= ATTENDANCE_ABSENCE_ALERT_COUNT
        or snapshot["recent_lates"] >= ATTENDANCE_LATE_ALERT_COUNT
    )
    if not has_attendance_alert:
        return InsightDecision(should_create=False)

    risk_band = (
        StudentInsight.RiskBand.HIGH
        if snapshot["recent_absences"] >= ATTENDANCE_ABSENCE_HIGH_RISK_COUNT
        else StudentInsight.RiskBand.MEDIUM
    )
    return InsightDecision(
        should_create=True,
        category=StudentInsight.Category.ATTENDANCE,
        risk_band=risk_band,
        title="Attendance pattern needs follow-up",
        concern_summary=(
            "Recent attendance patterns show repeated absences or lateness."
        ),
        evidence={
            "recent_absences": snapshot["recent_absences"],
            "recent_lates": snapshot["recent_lates"],
        },
        dedupe_key=(
            f"attendance:{student.id}:{snapshot['recent_absences']}:"
            f"{snapshot['recent_lates']}"
        ),
        suggested_actions=[
            "Talk with your child about what is affecting attendance.",
            "Plan for consistent arrival over the next week.",
            "Contact the school if support is needed.",
        ],
    )


def _score_chat_message(student: Student, source_id: str) -> InsightDecision:
    message = ChatMessage.objects.get(id=source_id)
    risk_band, tags = _classify_chat_message(message)
    if risk_band is None:
        return InsightDecision(should_create=False)

    return InsightDecision(
        should_create=True,
        category=StudentInsight.Category.COMMUNICATION,
        risk_band=risk_band,
        title="Teacher-parent communication follow-up",
        concern_summary=(
            "A recent school conversation suggests your child may need additional "
            "support."
        ),
        evidence={
            "tags": tags,
            "message_length": len(message.text or ""),
            "has_attachment": message.attachment_id is not None,
        },
        dedupe_key=f"communication:{student.id}:{':'.join(sorted(tags))}",
        suggested_actions=[
            "Review the concern discussed in the school message.",
            "Check in with your child about the issue.",
            "Reply to the teacher if more context is needed.",
        ],
    )


def score_student_risk(snapshot: dict[str, Any]) -> InsightDecision:
    event = snapshot["event"]
    event_type = event["source_event_type"]
    student = Student.objects.get(id=snapshot["student_id"])

    if event_type == StudentInsight.SourceEventType.ASSESSMENT_RESULT:
        return _score_assessment_result(
            snapshot=snapshot,
            student=student,
            source_id=event["source_id"],
        )
    if event_type in {
        StudentInsight.SourceEventType.ATTENDANCE,
        StudentInsight.SourceEventType.ATTENDANCE_REASON,
    }:
        return _score_attendance(snapshot, student)
    if event_type == StudentInsight.SourceEventType.CHAT_MESSAGE:
        return _score_chat_message(student, event["source_id"])
    return InsightDecision(should_create=False)


def generate_parent_guidance(
    insight_payload: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str]]:
    provider = _get_provider()
    try:
        generated = provider.generate(insight_payload)
    except Exception:
        fallback = _build_fallback_guidance(insight_payload)
        return fallback, StudentInsight.SafetyStatus.FALLBACK, ["provider_error"]

    result = {
        "title": generated.title,
        "summary": generated.summary,
        "recommended_actions": generated.recommended_actions,
        "confidence_label": generated.confidence_label,
    }
    approved, notes = _model_allowed_output(result, insight_payload)
    if approved:
        return result, StudentInsight.SafetyStatus.APPROVED, notes
    fallback = _build_fallback_guidance(insight_payload)
    return fallback, StudentInsight.SafetyStatus.FALLBACK, notes


def _build_redacted_payload(
    snapshot: dict[str, Any],
    decision: InsightDecision,
) -> dict[str, Any]:
    evidence = decision.evidence or {}
    tags = []
    if "tags" in evidence and isinstance(evidence["tags"], list):
        tags = [str(tag) for tag in evidence["tags"]]

    return {
        "category": decision.category,
        "risk_band": decision.risk_band,
        "concern_summary": decision.concern_summary,
        "evidence": evidence,
        "tags": tags,
        "student_context": {
            "grade_name": snapshot["grade_name"],
            "section_name": snapshot["section_name"],
        },
        "suggested_actions": decision.suggested_actions or [],
        "fallback_title": decision.title,
    }


def deliver_student_insight(student_insight_id: str) -> StudentInsight:
    insight = StudentInsight.objects.select_related("student").get(
        id=student_insight_id,
    )
    if insight.delivery_status != StudentInsight.DeliveryStatus.PENDING:
        return insight

    if insight.risk_band == StudentInsight.RiskBand.HIGH:
        insight.delivery_status = StudentInsight.DeliveryStatus.SUPPRESSED
        insight.save(update_fields=["delivery_status", "updated_at"])
        return insight

    notifications = [
        create_notification_once(
            recipient=link.parent.user,
            notifiable=insight,
            title=insight.title,
            message=insight.message,
            event_key=f"student_insight.delivered:{insight.id}:{link.parent.user_id}",
            data={
                "category": "insight",
                "insight_id": str(insight.id),
                "student_id": str(insight.student_id),
                "branch_id": str(insight.branch_id),
                "organization_id": str(insight.organization_id),
                "risk_band": insight.risk_band,
                "insight_category": insight.category.lower(),
                "confidence_label": insight.confidence_label,
                "target_route": f"/notifications?insightId={insight.id}",
            },
        )
        for link in _get_student_parents(insight.student)
    ]

    insight.delivery_status = (
        StudentInsight.DeliveryStatus.DELIVERED
        if notifications
        else StudentInsight.DeliveryStatus.SUPPRESSED
    )
    insight.delivered_at = timezone.now() if notifications else None
    insight.save(update_fields=["delivery_status", "delivered_at", "updated_at"])
    return insight


def _create_intervention_log(
    student: Student,
    decision: InsightDecision,
    event_context: EventContext,
) -> InterventionLog:
    return InterventionLog.objects.create(
        organization=student.organization,
        student=student,
        intervention_type={
            StudentInsight.Category.ACADEMICS: (
                InterventionLog.InterventionType.LOW_GRADE
            ),
            StudentInsight.Category.ATTENDANCE: (
                InterventionLog.InterventionType.ATTENDANCE
            ),
            StudentInsight.Category.ENGAGEMENT: InterventionLog.InterventionType.OTHER,
            StudentInsight.Category.COMMUNICATION: (
                InterventionLog.InterventionType.BEHAVIOUR
            ),
        }[decision.category],
        severity={
            StudentInsight.RiskBand.LOW: InterventionLog.Severity.LOW,
            StudentInsight.RiskBand.MEDIUM: InterventionLog.Severity.MEDIUM,
            StudentInsight.RiskBand.HIGH: InterventionLog.Severity.HIGH,
        }[decision.risk_band],
        status=InterventionLog.Status.OPEN,
        source_model=event_context.source_model,
        source_id=event_context.source_id,
        title=decision.title,
        description=decision.concern_summary,
    )


def _build_event_payload(
    *,
    source_event_type: str,
    source_model: str,
    source_id: str,
) -> dict[str, str]:
    return {
        "source_event_type": source_event_type,
        "source_model": source_model,
        "source_id": source_id,
    }


def _get_source_student_id(source_event_type: str, source: Any) -> str:
    if source_event_type == StudentInsight.SourceEventType.ATTENDANCE_REASON:
        return str(source.attendance.student_id)
    if source_event_type == StudentInsight.SourceEventType.CHAT_MESSAGE:
        return str(source.thread.student_id)
    return str(source.student_id)


def _resolve_event_source(
    *,
    source_event_type: str,
    source_id: str,
) -> tuple[Any, str]:
    source_mapping: dict[str, tuple[type[Any], str]] = {
        StudentInsight.SourceEventType.ASSESSMENT_RESULT: (
            AssessmentResult,
            "student_id",
        ),
        StudentInsight.SourceEventType.ATTENDANCE: (Attendance, "student_id"),
        StudentInsight.SourceEventType.ATTENDANCE_REASON: (
            AttendanceReason,
            "attendance__student_id",
        ),
        StudentInsight.SourceEventType.CHAT_MESSAGE: (
            ChatMessage,
            "thread__student_id",
        ),
    }
    model_class, _student_lookup = source_mapping[source_event_type]
    source = model_class.objects.get(id=source_id)
    return source, _get_source_student_id(source_event_type, source)


def _evaluate_event_candidate(
    *,
    student_id: str,
    source_event_type: str,
    source_model: str,
    source_id: str,
) -> tuple[dict[str, Any], InsightDecision]:
    snapshot = build_student_signal_snapshot(
        student_id,
        _build_event_payload(
            source_event_type=source_event_type,
            source_model=source_model,
            source_id=source_id,
        ),
    )
    decision = score_student_risk(snapshot)
    return snapshot, decision


def _create_or_reuse_student_insight(
    *,
    student: Student,
    event_context: EventContext,
    snapshot: dict[str, Any],
    decision: InsightDecision,
    audit_metadata: dict[str, Any] | None = None,
) -> InsightProcessingResult:
    if not decision.should_create:
        return InsightProcessingResult(insight=None, reused_existing=False)

    duplicate = _recent_duplicate(decision, student)
    if duplicate is not None and _severity_rank(duplicate.risk_band) >= _severity_rank(
        decision.risk_band,
    ):
        return InsightProcessingResult(insight=duplicate, reused_existing=True)

    redacted_payload = _build_redacted_payload(snapshot, decision)
    if audit_metadata is not None:
        redacted_payload["trigger_context"] = audit_metadata
    generated, safety_status, safety_notes = generate_parent_guidance(redacted_payload)
    intervention_log = None
    if decision.risk_band == StudentInsight.RiskBand.HIGH:
        intervention_log = _create_intervention_log(
            student,
            decision,
            event_context,
        )

    with transaction.atomic():
        insight = StudentInsight.objects.create(
            organization=student.organization,
            branch=student.branch,
            student=student,
            intervention_log=intervention_log,
            source_event_type=event_context.source_event_type,
            source_model=event_context.source_model,
            source_id=event_context.source_id,
            dedupe_key=decision.dedupe_key,
            category=decision.category,
            risk_band=decision.risk_band,
            title=generated["title"],
            message=generated["summary"],
            confidence_label=generated["confidence_label"],
            recommended_actions=generated["recommended_actions"],
            evidence={
                **(decision.evidence or {}),
                **(
                    {"trigger_context": audit_metadata}
                    if audit_metadata is not None
                    else {}
                ),
            },
            model_input_summary=redacted_payload,
            model_output=generated,
            safety_status=safety_status,
            safety_notes=safety_notes,
        )
        insight = deliver_student_insight(str(insight.id))
        return InsightProcessingResult(insight=insight, reused_existing=False)


def process_student_event(
    *,
    source_event_type: str,
    source_model: str,
    source_id: str,
) -> StudentInsight | None:
    event_context = EventContext(
        source_event_type=source_event_type,
        source_model=source_model,
        source_id=source_id,
    )
    source, student_id = _resolve_event_source(
        source_event_type=source_event_type,
        source_id=source_id,
    )
    del source
    snapshot, decision = _evaluate_event_candidate(
        student_id=student_id,
        source_event_type=source_event_type,
        source_model=source_model,
        source_id=source_id,
    )
    if not decision.should_create:
        return None

    student = Student.objects.select_related("organization", "branch").get(
        id=student_id,
    )
    result = _create_or_reuse_student_insight(
        student=student,
        event_context=event_context,
        snapshot=snapshot,
        decision=decision,
    )
    return result.insight


def _iter_manual_trigger_candidates(student: Student) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    academic_results = (
        AssessmentResult.objects.filter(
            student=student,
            obtained_marks__isnull=False,
        )
        .exclude(
            assessment__task_type=Assessment.TaskType.HOMEWORK,
        )
        .order_by("-created_at")[:5]
    )
    candidates.extend(
        [
            _build_event_payload(
                source_event_type=StudentInsight.SourceEventType.ASSESSMENT_RESULT,
                source_model="assessments.AssessmentResult",
                source_id=str(result.id),
            )
            for result in academic_results
        ],
    )

    attendance_records = Attendance.objects.filter(student=student).order_by(
        "-date",
        "-created_at",
    )[:5]
    candidates.extend(
        [
            _build_event_payload(
                source_event_type=StudentInsight.SourceEventType.ATTENDANCE,
                source_model="attendance.Attendance",
                source_id=str(record.id),
            )
            for record in attendance_records
        ],
    )

    homework_results = AssessmentResult.objects.filter(
        student=student,
        assessment__task_type=Assessment.TaskType.HOMEWORK,
    ).order_by("-created_at")[:5]
    candidates.extend(
        [
            _build_event_payload(
                source_event_type=StudentInsight.SourceEventType.ASSESSMENT_RESULT,
                source_model="assessments.AssessmentResult",
                source_id=str(result.id),
            )
            for result in homework_results
        ],
    )

    messages = ChatMessage.objects.filter(thread__student=student).order_by(
        "-created_at",
    )[:5]
    candidates.extend(
        [
            _build_event_payload(
                source_event_type=StudentInsight.SourceEventType.CHAT_MESSAGE,
                source_model="messaging.ChatMessage",
                source_id=str(message.id),
            )
            for message in messages
        ],
    )

    return candidates


def trigger_manual_student_insight(
    *,
    student_id: str,
    triggered_by_user: User,
) -> ManualInsightTriggerResult:
    student = Student.objects.select_related("organization", "branch").get(
        id=student_id,
    )
    audit_metadata = {
        "mode": "manual_trigger",
        "triggered_by_user_id": str(triggered_by_user.id),
        "triggered_at": timezone.now().isoformat(),
    }

    for candidate in _iter_manual_trigger_candidates(student):
        snapshot, decision = _evaluate_event_candidate(
            student_id=str(student.id),
            source_event_type=candidate["source_event_type"],
            source_model=candidate["source_model"],
            source_id=candidate["source_id"],
        )
        if not decision.should_create:
            continue

        result = _create_or_reuse_student_insight(
            student=student,
            event_context=EventContext(
                source_event_type=candidate["source_event_type"],
                source_model=candidate["source_model"],
                source_id=candidate["source_id"],
            ),
            snapshot=snapshot,
            decision=decision,
            audit_metadata=audit_metadata,
        )
        if result.insight is None:
            continue
        message = (
            "Existing recent insight reused."
            if result.reused_existing
            else "Insight generated and delivered through the parent notification flow."
        )
        return ManualInsightTriggerResult(
            created=True,
            insight=result.insight,
            reused_existing=result.reused_existing,
            message=message,
            source_event_type=candidate["source_event_type"],
            source_model=candidate["source_model"],
            source_id=candidate["source_id"],
        )

    return ManualInsightTriggerResult(
        created=False,
        reason_code="NO_QUALIFYING_SIGNAL",
        message=(
            "No current qualifying grade, attendance, homework, or message signal "
            "was found for this student."
        ),
    )
