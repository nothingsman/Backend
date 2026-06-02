from __future__ import annotations

from collections import Counter
from datetime import date
from datetime import datetime
from typing import TYPE_CHECKING

from accounts.models import User
from assessments.models import HomeworkConfirmation
from branches.models import BranchAdmin
from django.db.models import Count
from django.db.models.functions import ExtractYear
from students.models import Parent
from students.models import Student
from teachers.models import Teacher

if TYPE_CHECKING:
    from organizations.models import Organization


def build_organization_analytics_payload(
    organization: Organization,
) -> dict[str, object]:
    return {
        "organization_id": organization.id,
        "totals": {
            "students": Student.objects.filter(organization=organization).count(),
            "branch_admins": BranchAdmin.objects.filter(
                organization=organization,
            ).count(),
            "teachers": Teacher.objects.filter(organization=organization).count(),
            "parents": Parent.objects.filter(
                organizations=organization,
            )
            .distinct()
            .count(),
        },
        "student_enrollment_growth": _build_student_enrollment_growth(organization),
        "parent_engagement": _build_parent_engagement(organization),
    }


def _build_student_enrollment_growth(
    organization: Organization,
) -> list[dict[str, int]]:
    year_counts = Counter(
        _coerce_year(student.admission_date)
        for student in Student.objects.filter(
            organization=organization,
            admission_date__isnull=False,
        ).only("admission_date")
        if student.admission_date is not None
    )
    return [{"year": year, "count": year_counts[year]} for year in sorted(year_counts)]


def _build_parent_engagement(organization: Organization) -> list[dict[str, int]]:
    rows = (
        HomeworkConfirmation.objects.filter(
            organization=organization,
            is_confirmed=True,
            confirmed_at__isnull=False,
            confirmed_by__role=User.Role.PARENT,
        )
        .annotate(year=ExtractYear("confirmed_at"))
        .values("year")
        .annotate(count=Count("id"))
        .order_by("year")
    )
    return [{"year": _coerce_year(row["year"]), "count": row["count"]} for row in rows]


def _coerce_year(value: int | str | date | datetime | None) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value).year
    if isinstance(value, datetime):
        return value.year
    if isinstance(value, date):
        return value.year
    msg = "Year bucket cannot be null."
    raise ValueError(msg)
