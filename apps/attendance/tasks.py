from attendance.models import Attendance
from attendance.models import AttendanceSummary
from celery import shared_task
from django.db import DatabaseError
from django.utils import timezone
from notifications.producers import create_attendance_status_notifications


@shared_task(bind=True, max_retries=3)
def notify_parent_of_absence(self, attendance_id: str):
    """
    Creates in-app parent notifications for ABSENT/LATE attendance records.
    """
    try:
        record = (
            Attendance.objects.select_related("student", "section")
            .prefetch_related("student__parent_links__parent__user")
            .get(id=attendance_id)
        )

        create_attendance_status_notifications(record)

        return {
            "status": "queued",
            "attendance_id": attendance_id,
            "student_id": str(record.student_id),
            "triggered_at": timezone.now().isoformat(),
        }

    except (Attendance.DoesNotExist, DatabaseError) as exc:
        raise self.retry(exc=exc, countdown=60) from exc


@shared_task(bind=True, max_retries=3)
def refresh_attendance_summary(self, student_id: str, academic_year_id: str):
    """
    Recomputes the AttendanceSummary row for one student/year combination.
    Called after every Attendance save via Django signal.
    """
    try:
        qs = Attendance.objects.filter(
            student_id=student_id,
            academic_year_id=academic_year_id,
        )
        totals = {
            "total_present": qs.filter(status="PRESENT").count(),
            "total_absent": qs.filter(status="ABSENT").count(),
            "total_late": qs.filter(status="LATE").count(),
            "total_excused": qs.filter(status="EXCUSED").count(),
            "total_school_days": qs.count(),
        }

        # Fetch the first record to get organization FK
        first = qs.first()
        if first is None:
            return {"status": "no_records"}
    except DatabaseError as exc:
        raise self.retry(exc=exc, countdown=30) from exc
    else:
        AttendanceSummary.objects.update_or_create(
            student_id=student_id,
            academic_year_id=academic_year_id,
            defaults={**totals, "organization": first.organization},
        )
        return {"status": "updated", "student_id": student_id}
