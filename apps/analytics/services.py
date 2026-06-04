from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean

from academics.models import AcademicYear
from academics.models import Section
from academics.models import Subject
from analytics.models import InterventionLog
from assessments.models import Assessment
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceSummary
from django.db.models import Count
from django.db.models import Q
from django.utils import timezone
from messaging.models import ChatMessage
from student_insights.models import StudentInsight
from students.models import Student
from students.models import StudentAcademicYearSection
from teachers.models import TeacherSubjectAssignment

COMPLETED_SUBMISSION_STATUSES = {
    AssessmentResult.SubmissionStatus.SUBMITTED,
    AssessmentResult.SubmissionStatus.LATE,
    AssessmentResult.SubmissionStatus.GRADED,
}
ASSIGNMENT_TASK_TYPES = {
    "ASSIGNMENT",
    "HOMEWORK",
    "PROJECT",
    "LAB",
}
RISK_PRIORITY = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}
DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ANALYSIS_WINDOW_LABEL = "Current term · Last 4 weeks of activity"
TREND_SAMPLE_SIZE = 2
HIGH_RISK_GRADE_THRESHOLD = 50
MEDIUM_RISK_GRADE_THRESHOLD = 65
HIGH_RISK_ATTENDANCE_THRESHOLD = 75
MEDIUM_RISK_ATTENDANCE_THRESHOLD = 90
LOW_ATTENDANCE_HEADLINE_THRESHOLD = 85
LOW_GRADE_HEADLINE_THRESHOLD = 60
ACTION_GRADE_THRESHOLD = 70
HIGH_RISK_MISSING_THRESHOLD = 3
MEDIUM_RISK_MISSING_THRESHOLD = 1
GRADE_BAND_A_MIN = 85
GRADE_BAND_B_MIN = 70
GRADE_BAND_C_MIN = 50
PARENT_ENGAGEMENT_HIGH_MIN = 3
PARENT_ENGAGEMENT_MODERATE_MIN = 1


@dataclass(slots=True, frozen=True)
class GradeRecord:
    subject_id: str
    subject_name: str
    teacher_name: str | None
    label: str
    score: float
    recorded_at: object


def build_dashboard_overview_payload(
    *,
    section: Section,
    academic_year: AcademicYear,
    subject: Subject | None = None,
) -> dict[str, object]:
    student_ids = list(
        _get_dashboard_students(
            section=section,
            academic_year=academic_year,
        ).values_list("id", flat=True),
    )
    graded_results = list(
        _get_dashboard_graded_results(
            student_ids=student_ids,
            section=section,
            academic_year=academic_year,
            subject=subject,
        ),
    )
    student_averages = _build_student_average_percentages(graded_results)
    average_performance = _round_or_zero(_average(list(student_averages.values())))

    return {
        "total_students": len(student_ids),
        "average_performance": average_performance,
        "tasks_due": _get_tasks_due_count(
            section=section,
            academic_year=academic_year,
            subject=subject,
        ),
        "performance_distribution": _build_grade_band_distribution(student_averages),
        "parent_engagement": _build_parent_engagement_distribution(student_ids),
    }


def build_student_analytics_payload(student: Student) -> dict[str, object]:
    academic_year = _get_academic_year(student)
    graded_results = list(_get_graded_results(student, academic_year))
    assignment_results = list(_get_assignment_results(student, academic_year))
    peer_students = list(_get_peer_students(student))
    peer_grade_map = _build_peer_grade_map(peer_students, academic_year)
    latest_safe_insight = _get_latest_safe_insight(student)

    overall_grade = _round_or_zero(
        _average([result.percentage for result in graded_results]),
    )
    attendance_rate = _round_or_zero(_get_attendance_rate(student, academic_year))
    assignment_summary = _build_assignment_summary(assignment_results)
    trend_delta, trend_direction = _build_trend_summary(graded_results)
    class_average_overall = _round_or_none(
        _average(list(peer_grade_map.values())),
    )
    class_rank = _compute_class_rank(student, overall_grade, peer_grade_map)
    class_size = len(peer_students) if peer_students else None
    subject_performance = _build_subject_performance(
        graded_results,
        peer_students,
        academic_year,
        student,
    )
    heatmap = _build_submission_heatmap(assignment_results)
    recommended_actions = _build_recommended_actions(
        latest_safe_insight=latest_safe_insight,
        overall_grade=overall_grade,
        attendance_rate=attendance_rate,
        assignment_summary=assignment_summary,
        trend_direction=trend_direction,
    )
    risk_band = _derive_risk_band(
        student=student,
        latest_safe_insight=latest_safe_insight,
        overall_grade=overall_grade,
        attendance_rate=attendance_rate,
        missing_assignments=assignment_summary["missing_assignments"],
    )

    return {
        "student_id": student.id,
        "generated_at": timezone.now(),
        "analysis_window_label": ANALYSIS_WINDOW_LABEL,
        "summary": {
            "overall_grade": overall_grade,
            "attendance_rate": attendance_rate,
            "assignment_completion_rate": assignment_summary[
                "assignment_completion_rate"
            ],
            "completed_assignments": assignment_summary["completed_assignments"],
            "pending_assignments": assignment_summary["pending_assignments"],
            "missing_assignments": assignment_summary["missing_assignments"],
            "class_average_overall": class_average_overall,
            "class_rank": class_rank,
            "class_size": class_size,
            "risk_band": risk_band,
            "trend_direction": trend_direction,
            "trend_delta": trend_delta,
            "headline_insight": _build_headline_insight(
                latest_safe_insight=latest_safe_insight,
                overall_grade=overall_grade,
                attendance_rate=attendance_rate,
                missing_assignments=assignment_summary["missing_assignments"],
            ),
        },
        "subject_performance": subject_performance,
        "grade_trend": {
            "series": _build_grade_trend_series(graded_results),
        },
        "submission_heatmap": heatmap,
        "recommended_actions": recommended_actions,
    }


def _get_dashboard_students(
    *,
    section: Section,
    academic_year: AcademicYear,
):
    student_ids_for_year = StudentAcademicYearSection.objects.filter(
        academic_year=academic_year,
        section=section,
    ).values_list("student_id", flat=True)

    return Student.objects.filter(
        Q(id__in=student_ids_for_year) | Q(current_section=section),
        organization=section.organization,
        branch=section.branch,
    ).distinct()


def _get_dashboard_graded_results(
    *,
    student_ids: list[str],
    section: Section,
    academic_year: AcademicYear,
    subject: Subject | None,
):
    queryset = (
        AssessmentResult.objects.select_related(
            "assessment",
            "assessment__teacher_assignment__subject",
        )
        .filter(
            student_id__in=student_ids,
            assessment__teacher_assignment__section=section,
            assessment__teacher_assignment__academic_year=academic_year,
            obtained_marks__isnull=False,
        )
        .order_by("student_id", "created_at", "id")
    )
    if subject is not None:
        queryset = queryset.filter(assessment__teacher_assignment__subject=subject)
    return queryset


def _build_student_average_percentages(
    graded_results: list[AssessmentResult],
) -> dict[str, float]:
    grouped_scores: dict[str, list[float]] = defaultdict(list)
    for result in graded_results:
        if result.percentage is not None:
            grouped_scores[str(result.student_id)].append(result.percentage)

    return {
        student_id: round(mean(scores), 2)
        for student_id, scores in grouped_scores.items()
        if scores
    }


def _get_tasks_due_count(
    *,
    section: Section,
    academic_year: AcademicYear,
    subject: Subject | None,
) -> int:
    queryset = Assessment.objects.filter(
        teacher_assignment__section=section,
        teacher_assignment__academic_year=academic_year,
        status=Assessment.Status.PUBLISHED,
        due_date__gte=timezone.localdate(),
    )
    if subject is not None:
        queryset = queryset.filter(teacher_assignment__subject=subject)
    return queryset.count()


def _build_grade_band_distribution(
    student_averages: dict[str, float],
) -> dict[str, int]:
    distribution = {"A": 0, "B": 0, "C": 0, "F": 0}
    for percentage in student_averages.values():
        distribution[_grade_band_for_percentage(percentage)] += 1
    return distribution


def _grade_band_for_percentage(percentage: float) -> str:
    if percentage >= GRADE_BAND_A_MIN:
        return "A"
    if percentage >= GRADE_BAND_B_MIN:
        return "B"
    if percentage >= GRADE_BAND_C_MIN:
        return "C"
    return "F"


def _build_parent_engagement_distribution(student_ids: list[str]) -> dict[str, int]:
    distribution = {"high": 0, "moderate": 0, "low": 0}
    if not student_ids:
        return distribution

    message_counts: dict[str, int] = defaultdict(int)
    for student_id, count in (
        ChatMessage.objects.filter(
            thread__student_id__in=student_ids,
            sender__role="PARENT",
        )
        .values_list("thread__student_id")
        .annotate(message_count=Count("id"))
    ):
        message_counts[str(student_id)] = count

    for student_id in student_ids:
        count = message_counts.get(str(student_id), 0)
        if count >= PARENT_ENGAGEMENT_HIGH_MIN:
            distribution["high"] += 1
        elif count >= PARENT_ENGAGEMENT_MODERATE_MIN:
            distribution["moderate"] += 1
        else:
            distribution["low"] += 1

    return distribution


def _get_academic_year(student: Student) -> AcademicYear | None:
    if student.current_section_id and student.current_section.academic_year_id:
        return student.current_section.academic_year

    return (
        AcademicYear.objects.filter(
            organization=student.organization,
            branch=student.branch,
            is_current=True,
        )
        .order_by("-start_date")
        .first()
    )


def _get_graded_results(student: Student, academic_year: AcademicYear | None):
    queryset = (
        AssessmentResult.objects.select_related(
            "assessment__teacher_assignment__subject",
            "assessment__teacher_assignment__teacher__user",
        )
        .filter(
            student=student,
            obtained_marks__isnull=False,
        )
        .order_by("created_at", "id")
    )
    if academic_year is not None:
        queryset = queryset.filter(
            assessment__teacher_assignment__academic_year=academic_year,
        )
    return queryset


def _get_assignment_results(student: Student, academic_year: AcademicYear | None):
    queryset = (
        AssessmentResult.objects.select_related("assessment")
        .filter(
            student=student,
            assessment__task_type__in=ASSIGNMENT_TASK_TYPES,
        )
        .order_by("created_at", "id")
    )
    if academic_year is not None:
        queryset = queryset.filter(
            assessment__teacher_assignment__academic_year=academic_year,
        )
    return queryset


def _get_peer_students(student: Student):
    if student.current_section_id is None:
        return Student.objects.none()

    return Student.objects.filter(current_section=student.current_section).only("id")


def _build_peer_grade_map(
    peer_students: list[Student],
    academic_year: AcademicYear | None,
) -> dict[str, float]:
    if not peer_students:
        return {}

    queryset = AssessmentResult.objects.filter(
        student_id__in=[peer.id for peer in peer_students],
        obtained_marks__isnull=False,
    ).select_related("assessment")
    if academic_year is not None:
        queryset = queryset.filter(
            assessment__teacher_assignment__academic_year=academic_year,
        )

    grouped_scores: dict[str, list[float]] = defaultdict(list)
    for result in queryset:
        if result.percentage is not None:
            grouped_scores[str(result.student_id)].append(result.percentage)

    return {
        student_id: round(mean(scores), 2)
        for student_id, scores in grouped_scores.items()
        if scores
    }


def _get_attendance_rate(student: Student, academic_year: AcademicYear | None) -> float:
    summary = None
    if academic_year is not None:
        summary = AttendanceSummary.objects.filter(
            student=student,
            academic_year=academic_year,
        ).first()
    if summary is None:
        summary = (
            AttendanceSummary.objects.filter(student=student)
            .order_by("-academic_year__start_date")
            .first()
        )
    if summary is not None:
        return float(summary.attendance_rate)

    attendance_queryset = Attendance.objects.filter(student=student)
    if academic_year is not None:
        attendance_queryset = attendance_queryset.filter(academic_year=academic_year)

    records = list(attendance_queryset.only("status"))
    total = len(records)
    if total == 0:
        return 0.0

    present_like = sum(
        1
        for record in records
        if record.status in {Attendance.Status.PRESENT, Attendance.Status.EXCUSED}
    )
    return round((present_like / total) * 100, 2)


def _build_assignment_summary(
    assignment_results: list[AssessmentResult],
) -> dict[str, float | int]:
    completed = sum(
        1
        for result in assignment_results
        if result.submission_status in COMPLETED_SUBMISSION_STATUSES
    )
    pending = sum(
        1
        for result in assignment_results
        if result.submission_status == AssessmentResult.SubmissionStatus.PENDING
    )
    missing = sum(
        1
        for result in assignment_results
        if result.submission_status == AssessmentResult.SubmissionStatus.MISSING
    )
    total = len(assignment_results)
    completion_rate = round((completed / total) * 100, 2) if total else 0.0

    return {
        "assignment_completion_rate": completion_rate,
        "completed_assignments": completed,
        "pending_assignments": pending,
        "missing_assignments": missing,
    }


def _build_trend_summary(
    graded_results: list[AssessmentResult],
) -> tuple[float, str]:
    percentages = [
        result.percentage for result in graded_results if result.percentage is not None
    ]
    if len(percentages) < TREND_SAMPLE_SIZE:
        return 0.0, "steady"

    latest = percentages[-1]
    previous = percentages[-(TREND_SAMPLE_SIZE + 1) : -1]
    delta = round(latest - mean(previous), 2)
    if delta > 1:
        return delta, "up"
    if delta < -1:
        return delta, "down"
    return delta, "steady"


def _compute_class_rank(
    student: Student,
    overall_grade: float,
    peer_grade_map: dict[str, float],
) -> int | None:
    student_grade = peer_grade_map.get(
        str(student.id),
        overall_grade if overall_grade > 0 else None,
    )
    if student_grade is None:
        return None

    ranked_scores = sorted(set(peer_grade_map.values()), reverse=True)
    for index, score in enumerate(ranked_scores, start=1):
        if student_grade >= score:
            return index
    return len(ranked_scores) + 1 if ranked_scores else None


def _build_subject_performance(
    graded_results: list[AssessmentResult],
    peer_students: list[Student],
    academic_year: AcademicYear | None,
    student: Student,
) -> list[dict[str, object]]:
    subject_scores: dict[str, list[float]] = defaultdict(list)
    subject_names: dict[str, str] = {}
    for result in graded_results:
        if result.percentage is None:
            continue
        subject = result.assessment.teacher_assignment.subject
        subject_id = str(subject.id)
        subject_scores[subject_id].append(result.percentage)
        subject_names[subject_id] = subject.name

    if not subject_scores:
        return []

    peer_class_averages = _build_peer_subject_average_map(
        peer_students=peer_students,
        academic_year=academic_year,
    )
    teacher_name_map = _build_teacher_name_map(student, academic_year)

    rows = []
    for subject_id, scores in sorted(
        subject_scores.items(),
        key=lambda item: subject_names[item[0]].lower(),
    ):
        rows.append(
            {
                "subject": subject_names[subject_id],
                "student_score": round(mean(scores), 2),
                "class_average": round(peer_class_averages.get(subject_id, 0.0), 2),
                "target_score": None,
                "teacher_name": teacher_name_map.get(subject_id),
                "color": None,
            },
        )
    return rows


def _build_peer_subject_average_map(
    *,
    peer_students: list[Student],
    academic_year: AcademicYear | None,
) -> dict[str, float]:
    if not peer_students:
        return {}

    queryset = AssessmentResult.objects.select_related(
        "assessment__teacher_assignment__subject",
    ).filter(
        student_id__in=[student.id for student in peer_students],
        obtained_marks__isnull=False,
    )
    if academic_year is not None:
        queryset = queryset.filter(
            assessment__teacher_assignment__academic_year=academic_year,
        )

    grouped_scores: dict[str, list[float]] = defaultdict(list)
    for result in queryset:
        if result.percentage is None:
            continue
        grouped_scores[str(result.assessment.teacher_assignment.subject_id)].append(
            result.percentage,
        )

    return {
        subject_id: mean(scores)
        for subject_id, scores in grouped_scores.items()
        if scores
    }


def _build_teacher_name_map(
    student: Student,
    academic_year: AcademicYear | None,
) -> dict[str, str | None]:
    if student.current_section_id is None:
        return {}

    queryset = TeacherSubjectAssignment.objects.select_related("teacher__user").filter(
        section=student.current_section,
    )
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)

    return {
        str(assignment.subject_id): assignment.teacher.user.name or None
        for assignment in queryset
    }


def _build_grade_trend_series(
    graded_results: list[AssessmentResult],
) -> list[dict[str, object]]:
    grouped_records: dict[str, list[GradeRecord]] = defaultdict(list)
    for result in graded_results:
        if result.percentage is None:
            continue
        subject = result.assessment.teacher_assignment.subject
        teacher = result.assessment.teacher_assignment.teacher.user
        grouped_records[subject.name].append(
            GradeRecord(
                subject_id=str(subject.id),
                subject_name=subject.name,
                teacher_name=teacher.name or None,
                label=result.assessment.title,
                score=result.percentage,
                recorded_at=result.created_at,
            ),
        )

    series = []
    for subject_name in sorted(grouped_records):
        points = [
            {
                "label": record.label,
                "score": round(record.score, 2),
                "recorded_at": record.recorded_at,
            }
            for record in grouped_records[subject_name]
        ]
        series.append(
            {
                "subject": subject_name,
                "color": None,
                "points": points,
            },
        )
    return series


def _build_submission_heatmap(
    assignment_results: list[AssessmentResult],
) -> list[dict[str, object]]:
    end_date = timezone.localdate()
    start_date = end_date - timedelta(days=27)
    counts: dict[object, int] = defaultdict(int)

    for result in assignment_results:
        if result.submission_status not in COMPLETED_SUBMISSION_STATUSES:
            continue
        activity_date = timezone.localtime(result.created_at).date()
        if start_date <= activity_date <= end_date:
            counts[activity_date] += 1

    cells = []
    for index in range(28):
        current_date = start_date + timedelta(days=index)
        weekday = current_date.weekday()
        cells.append(
            {
                "date": current_date,
                "week": (index // 7) + 1,
                "weekday": weekday,
                "day_label": DAY_LABELS[weekday],
                "submission_count": counts.get(current_date, 0),
            },
        )
    return cells


def _get_latest_safe_insight(student: Student) -> StudentInsight | None:
    return (
        StudentInsight.objects.filter(
            student=student,
            safety_status__in=[
                StudentInsight.SafetyStatus.APPROVED,
                StudentInsight.SafetyStatus.FALLBACK,
            ],
            delivery_status=StudentInsight.DeliveryStatus.DELIVERED,
        )
        .order_by("-created_at")
        .first()
    )


def _derive_risk_band(
    *,
    student: Student,
    latest_safe_insight: StudentInsight | None,
    overall_grade: float,
    attendance_rate: float,
    missing_assignments: int,
) -> str:
    candidates = ["unknown"]
    if latest_safe_insight is not None:
        candidates.append(latest_safe_insight.risk_band.lower())

    if overall_grade == 0 and attendance_rate == 0 and missing_assignments == 0:
        return max(candidates, key=RISK_PRIORITY.get)
    if (
        overall_grade < HIGH_RISK_GRADE_THRESHOLD
        or attendance_rate < HIGH_RISK_ATTENDANCE_THRESHOLD
        or missing_assignments >= HIGH_RISK_MISSING_THRESHOLD
    ):
        candidates.append("high")
    elif (
        overall_grade < MEDIUM_RISK_GRADE_THRESHOLD
        or attendance_rate < MEDIUM_RISK_ATTENDANCE_THRESHOLD
        or missing_assignments >= MEDIUM_RISK_MISSING_THRESHOLD
    ):
        candidates.append("medium")
    else:
        candidates.append("low")

    intervention = (
        InterventionLog.objects.filter(
            student=student,
            status__in=[
                InterventionLog.Status.OPEN,
                InterventionLog.Status.IN_PROGRESS,
            ],
        )
        .order_by("-created_at")
        .first()
    )
    if intervention is not None:
        if intervention.severity in {
            InterventionLog.Severity.HIGH,
            InterventionLog.Severity.CRITICAL,
        }:
            candidates.append("high")
        elif intervention.severity == InterventionLog.Severity.MEDIUM:
            candidates.append("medium")

    return max(candidates, key=RISK_PRIORITY.get)


def _build_headline_insight(
    *,
    latest_safe_insight: StudentInsight | None,
    overall_grade: float,
    attendance_rate: float,
    missing_assignments: int,
) -> str | None:
    if latest_safe_insight is not None:
        return latest_safe_insight.title
    if missing_assignments >= HIGH_RISK_MISSING_THRESHOLD:
        return "Multiple assignments still need follow-up."
    if attendance_rate and attendance_rate < LOW_ATTENDANCE_HEADLINE_THRESHOLD:
        return "Attendance needs attention this term."
    if overall_grade and overall_grade < LOW_GRADE_HEADLINE_THRESHOLD:
        return "Recent grades show the student may need extra support."
    return None


def _build_recommended_actions(
    *,
    latest_safe_insight: StudentInsight | None,
    overall_grade: float,
    attendance_rate: float,
    assignment_summary: dict[str, float | int],
    trend_direction: str,
) -> list[str]:
    if latest_safe_insight is not None and latest_safe_insight.recommended_actions:
        actions = [
            _sanitize_action(action)
            for action in latest_safe_insight.recommended_actions
            if _sanitize_action(action) is not None
        ]
        if actions:
            return actions[:3]

    fallback_actions: list[str] = []
    if assignment_summary["missing_assignments"] > 0:
        fallback_actions.append(
            "Review missing assignments with your child and set a completion "
            "plan for this week.",
        )
    if attendance_rate < MEDIUM_RISK_ATTENDANCE_THRESHOLD:
        fallback_actions.append(
            "Talk through recent absences or lateness and remove any barriers "
            "to daily attendance.",
        )
    if overall_grade < ACTION_GRADE_THRESHOLD:
        fallback_actions.append(
            "Ask the teacher which topic needs the most support before the next "
            "assessment.",
        )
    if trend_direction == "down":
        fallback_actions.append(
            "Check the recent grade trend with your child and agree on one "
            "short study goal.",
        )
    if not fallback_actions:
        fallback_actions.extend(
            [
                "Review this week's school progress with your child.",
                "Praise consistent effort and ask if any subject needs extra help.",
            ],
        )
    return fallback_actions[:3]


def _sanitize_action(action: object) -> str | None:
    if not isinstance(action, str):
        return None
    cleaned = " ".join(action.split()).strip()
    if not cleaned:
        return None
    return cleaned[:160]


def _average(values: list[float | None]) -> float | None:
    numeric_values = [value for value in values if value is not None]
    if not numeric_values:
        return None
    return mean(numeric_values)


def _round_or_zero(value: float | None) -> float:
    return round(value or 0.0, 2)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)
