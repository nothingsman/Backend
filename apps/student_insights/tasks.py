from celery import shared_task
from django.db import DatabaseError
from django.utils import timezone
from student_insights.services import process_student_event


@shared_task(bind=True, max_retries=3)
def process_student_insight_event(
    self,
    *,
    source_event_type: str,
    source_model: str,
    source_id: str,
):
    try:
        insight = process_student_event(
            source_event_type=source_event_type,
            source_model=source_model,
            source_id=source_id,
        )
    except DatabaseError as exc:
        raise self.retry(exc=exc, countdown=30) from exc

    return {
        "status": "processed" if insight is not None else "skipped",
        "source_event_type": source_event_type,
        "source_model": source_model,
        "source_id": source_id,
        "insight_id": str(insight.id) if insight is not None else None,
        "processed_at": timezone.now().isoformat(),
    }

