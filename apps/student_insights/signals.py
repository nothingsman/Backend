from assessments.models import AssessmentResult
from attendance.models import Attendance
from attendance.models import AttendanceReason
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from messaging.models import ChatMessage
from student_insights.models import StudentInsight
from student_insights.tasks import process_student_insight_event


def _enqueue(source_event_type: str, source_model: str, source_id: str) -> None:
    transaction.on_commit(
        lambda: process_student_insight_event.delay(
            source_event_type=source_event_type,
            source_model=source_model,
            source_id=source_id,
        ),
    )


@receiver(post_save, sender=AssessmentResult)
def enqueue_assessment_result_insight(sender, instance: AssessmentResult, **kwargs):
    del sender, kwargs
    _enqueue(
        StudentInsight.SourceEventType.ASSESSMENT_RESULT,
        "assessments.AssessmentResult",
        str(instance.id),
    )


@receiver(post_save, sender=Attendance)
def enqueue_attendance_insight(sender, instance: Attendance, **kwargs):
    del sender, kwargs
    _enqueue(
        StudentInsight.SourceEventType.ATTENDANCE,
        "attendance.Attendance",
        str(instance.id),
    )


@receiver(post_save, sender=AttendanceReason)
def enqueue_attendance_reason_insight(sender, instance: AttendanceReason, **kwargs):
    del sender, kwargs
    _enqueue(
        StudentInsight.SourceEventType.ATTENDANCE_REASON,
        "attendance.AttendanceReason",
        str(instance.id),
    )


@receiver(post_save, sender=ChatMessage)
def enqueue_chat_message_insight(
    sender,
    instance: ChatMessage,
    **kwargs,
):
    created = kwargs.get("created", False)
    del sender, kwargs
    if created:
        _enqueue(
            StudentInsight.SourceEventType.CHAT_MESSAGE,
            "messaging.ChatMessage",
            str(instance.id),
        )
