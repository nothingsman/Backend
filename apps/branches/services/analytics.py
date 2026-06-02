from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from academics.models import AcademicYear
from academics.models import Grade
from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceSummary
from branches.models import Branch
from branches.models import BranchAdmin
from django.db.models import F
from students.models import Student
from students.models import StudentAcademicYearSection
from teachers.models import Teacher

if TYPE_CHECKING:
    from datetime import date
    from datetime import datetime


def build_branch_analytics_payload(branch: Branch) -> dict[str, object]:
    current_academic_year = _get_current_academic_year(branch)
    active_students = Student.objects.filter(
        branch=branch,
        status=Student.Status.ACTIVE,
    )
    active_student_count = active_students.count()
    active_teacher_count = Teacher.objects.filter(
        branch=branch,
        user__is_active=True,
    ).count()

    return {
        "branch_id": branch.id,
        "totals": {
            "active_students": active_student_count,
            "active_teachers": active_teacher_count,
            "active_branch_admins": BranchAdmin.objects.filter(
                branch=branch,
                status=BranchAdmin.Status.ACTIVE,
                user__is_active=True,
            ).count(),
        },
        "attendance_rate": _build_branch_attendance_rate(
            branch,
            current_academic_year,
        ),
        "performance_risk": _build_branch_performance_risk(
            branch,
            active_student_count,
        ),
        "teacher_count": active_teacher_count,
        "parent_linkage_percent": _build_parent_linkage_percent(
            active_students,
            active_student_count,
        ),
        "attendance_trend": {
            "weekly": _build_attendance_trend(branch, "weekly"),
            "monthly": _build_attendance_trend(branch, "monthly"),
            "annual": _build_attendance_trend(branch, "annual"),
        },
        "per_grade": _build_per_grade_performance(
            branch,
            current_academic_year,
        ),
        "academic_performance_index": {
            "annual": _build_annual_academic_performance_index(branch),
            "quarterly": _build_quarterly_academic_performance_index(branch),
        },
    }


def build_top_performance_risks_payload(
    branch: Branch,
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    current_academic_year = _get_current_academic_year(branch)
    grade_assignments = _grade_assignment_map(branch, current_academic_year)
    rows = (
        AssessmentResult.objects.filter(
            assessment__branch=branch,
            student__status=Student.Status.ACTIVE,
            obtained_marks__isnull=False,
            assessment__passing_marks__isnull=False,
        )
        .select_related("student", "assessment")
        .only(
            "id",
            "student_id",
            "student__first_name",
            "student__last_name",
            "student__roll_no",
            "obtained_marks",
            "created_at",
            "assessment__total_marks",
            "assessment__passing_marks",
        )
    )

    buckets: dict[str, _RiskAccumulator] = {}
    for result in rows:
        if not result.is_below_passing:
            continue
        student_id = str(result.student_id)
        accumulator = buckets.setdefault(
            student_id,
            _RiskAccumulator(
                student_id=result.student_id,
                student_name=f"{result.student.first_name} {result.student.last_name}",
                roll_no=result.student.roll_no,
                percentages=[],
                latest_risk_at=result.created_at,
            ),
        )
        accumulator.percentages.append(_result_percentage(result))
        accumulator.latest_risk_at = max(
            accumulator.latest_risk_at,
            result.created_at,
        )

    ranked = sorted(
        (
            {
                "student_id": accumulator.student_id,
                "student_name": accumulator.student_name,
                "roll_no": accumulator.roll_no,
                "grade_id": grade_info.get("grade_id"),
                "grade_name": grade_info.get("grade_name"),
                "risk_count": len(accumulator.percentages),
                "average_percentage": _average(accumulator.percentages),
                "latest_risk_at": accumulator.latest_risk_at,
            }
            for accumulator in buckets.values()
            for grade_info in [grade_assignments.get(str(accumulator.student_id), {})]
        ),
        key=lambda item: (
            -int(item["risk_count"]),
            float(item["average_percentage"]),
            -item["latest_risk_at"].timestamp(),
        ),
    )
    return ranked[:limit]


def _build_annual_academic_performance_index(
    branch: Branch,
) -> list[dict[str, int | float]]:
    buckets: dict[int, list[float]] = defaultdict(list)
    for result in _iter_graded_branch_results(branch):
        buckets[result.created_at.year].append(_result_percentage(result))

    return [
        {
            "year": year,
            "average_percentage": _average(percentages),
        }
        for year, percentages in sorted(buckets.items())
    ]


def _build_quarterly_academic_performance_index(
    branch: Branch,
) -> list[dict[str, int | float]]:
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for result in _iter_graded_branch_results(branch):
        quarter = ((result.created_at.month - 1) // 3) + 1
        buckets[(result.created_at.year, quarter)].append(_result_percentage(result))

    return [
        {
            "year": year,
            "quarter": quarter,
            "average_percentage": _average(percentages),
        }
        for (year, quarter), percentages in sorted(buckets.items())
    ]


def _iter_graded_branch_results(branch: Branch):
    return (
        AssessmentResult.objects.filter(
            assessment__branch=branch,
            obtained_marks__isnull=False,
        )
        .select_related("assessment")
        .only("obtained_marks", "created_at", "assessment__total_marks")
    )


def _build_branch_attendance_rate(
    branch: Branch,
    academic_year: AcademicYear | None,
) -> float:
    if academic_year is None:
        return 0.0

    summaries = AttendanceSummary.objects.filter(
        student__branch=branch,
        student__status=Student.Status.ACTIVE,
        academic_year=academic_year,
    )

    present = 0
    excused = 0
    total_days = 0
    for summary in summaries.only(
        "total_present",
        "total_excused",
        "total_school_days",
    ):
        present += summary.total_present
        excused += summary.total_excused
        total_days += summary.total_school_days

    if total_days == 0:
        return 0.0
    return round((present + excused) / total_days * 100, 2)


def _build_branch_performance_risk(
    branch: Branch,
    active_student_count: int,
) -> dict[str, int | float]:
    at_risk_students = (
        AssessmentResult.objects.filter(
            assessment__branch=branch,
            student__status=Student.Status.ACTIVE,
            obtained_marks__isnull=False,
            assessment__passing_marks__isnull=False,
            obtained_marks__lt=F("assessment__passing_marks"),
        )
        .values("student_id")
        .distinct()
        .count()
    )
    percent = 0.0
    if active_student_count:
        percent = round(at_risk_students / active_student_count * 100, 2)
    return {
        "at_risk_students": at_risk_students,
        "percent": percent,
    }


def _build_parent_linkage_percent(
    active_students,
    active_student_count: int,
) -> float:
    if active_student_count == 0:
        return 0.0
    linked_students = (
        active_students.filter(parent_links__isnull=False).distinct().count()
    )
    return round(linked_students / active_student_count * 100, 2)


def _build_attendance_trend(
    branch: Branch,
    period: str,
) -> list[dict[str, object]]:
    records = Attendance.objects.filter(branch=branch).only("date", "status")
    buckets: dict[object, dict[str, int]] = defaultdict(
        lambda: {"present_equivalent": 0, "total": 0},
    )

    for record in records:
        bucket = _attendance_bucket_key(record.date, period)
        buckets[bucket]["total"] += 1
        if record.status in {Attendance.Status.PRESENT, Attendance.Status.EXCUSED}:
            buckets[bucket]["present_equivalent"] += 1

    return [
        _attendance_bucket_payload(bucket, counts, period)
        for bucket, counts in sorted(buckets.items())
    ]


def _build_per_grade_performance(
    branch: Branch,
    academic_year: AcademicYear | None,
) -> list[dict[str, object]]:
    grade_assignments = _grade_assignment_map(branch, academic_year)
    student_count_by_grade: dict[str, int] = defaultdict(int)
    for grade_info in grade_assignments.values():
        grade_id = grade_info["grade_id"]
        if grade_id is not None:
            student_count_by_grade[grade_id] += 1

    percentages_by_grade: dict[str, list[float]] = defaultdict(list)
    results = (
        AssessmentResult.objects.filter(
            assessment__branch=branch,
            obtained_marks__isnull=False,
        )
        .select_related("assessment")
        .only(
            "student_id",
            "obtained_marks",
            "assessment__total_marks",
        )
    )
    for result in results:
        grade_info = grade_assignments.get(str(result.student_id))
        if not grade_info or grade_info["grade_id"] is None:
            continue
        percentages_by_grade[grade_info["grade_id"]].append(_result_percentage(result))

    ordered_grades = Grade.objects.filter(branch=branch).order_by("level", "name")
    return [
        {
            "grade_id": grade.id,
            "grade_name": grade.name,
            "student_count": student_count_by_grade.get(str(grade.id), 0),
            "performance_score": _average(percentages_by_grade[str(grade.id)])
            if percentages_by_grade.get(str(grade.id))
            else 0.0,
        }
        for grade in ordered_grades
    ]


def _get_current_academic_year(branch: Branch) -> AcademicYear | None:
    return branch.academic_years.filter(is_current=True).first()


def _grade_assignment_map(
    branch: Branch,
    academic_year: AcademicYear | None,
) -> dict[str, dict[str, str | None]]:
    queryset = StudentAcademicYearSection.objects.filter(
        student__branch=branch,
        student__status=Student.Status.ACTIVE,
    ).select_related("student", "section__grade")
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)
    else:
        queryset = queryset.filter(student__current_section__isnull=False)

    assignments = {
        str(item.student_id): {
            "grade_id": str(item.section.grade_id) if item.section_id else None,
            "grade_name": item.section.grade.name if item.section_id else None,
        }
        for item in queryset
        if item.section_id is not None
    }

    if assignments:
        return assignments

    fallback_students = Student.objects.filter(
        branch=branch,
        status=Student.Status.ACTIVE,
        current_section__isnull=False,
    ).select_related("current_section__grade")
    return {
        str(student.id): {
            "grade_id": str(student.current_section.grade_id),
            "grade_name": student.current_section.grade.name,
        }
        for student in fallback_students
    }


def _attendance_bucket_key(value: date, period: str) -> object:
    if period == "weekly":
        iso_year, iso_week, _ = value.isocalendar()
        return iso_year, iso_week
    if period == "monthly":
        return value.year, value.month
    if period == "annual":
        return value.year
    msg = f"Unsupported attendance trend period: {period}"
    raise ValueError(msg)


def _attendance_bucket_payload(
    bucket: object,
    counts: dict[str, int],
    period: str,
) -> dict[str, object]:
    total = counts["total"]
    attendance_rate = 0.0
    if total:
        attendance_rate = round(counts["present_equivalent"] / total * 100, 2)

    if period == "weekly":
        year, week = bucket
        return {
            "year": year,
            "week": week,
            "attendance_rate": attendance_rate,
        }
    if period == "monthly":
        year, month = bucket
        return {
            "year": year,
            "month": month,
            "attendance_rate": attendance_rate,
        }
    return {
        "year": bucket,
        "attendance_rate": attendance_rate,
    }


def _result_percentage(result: AssessmentResult) -> float:
    obtained_marks = result.obtained_marks
    if obtained_marks is None:
        msg = "Cannot calculate percentage for an ungraded result."
        raise ValueError(msg)

    percentage = obtained_marks / result.assessment.total_marks * Decimal("100")
    return round(float(percentage), 2)


def _average(percentages: list[float]) -> float:
    return round(sum(percentages) / len(percentages), 2)


@dataclass
class _RiskAccumulator:
    student_id: object
    student_name: str
    roll_no: str
    percentages: list[float]
    latest_risk_at: datetime
