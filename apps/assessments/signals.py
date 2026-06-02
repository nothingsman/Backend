from analytics.models import InterventionLog
from assessments.models import Assessment
from assessments.models import AssessmentResult
from django.db import transaction
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.dispatch import receiver
from notifications.producers import create_assessment_graded_notifications
from notifications.producers import create_assessment_published_notifications

HIGH_SEVERITY_RATIO_THRESHOLD = 0.50
MEDIUM_SEVERITY_RATIO_THRESHOLD = 0.80


@receiver(pre_save, sender=Assessment)
def cache_previous_assessment_status(sender, instance: Assessment, **kwargs):
    del sender, kwargs
    instance.previous_status = None
    if instance.pk:
        instance.previous_status = (
            Assessment.objects.filter(pk=instance.pk)
            .values_list("status", flat=True)
            .first()
        )


@receiver(post_save, sender=Assessment)
def create_assessment_publish_notifications(
    sender,
    instance: Assessment,
    created,
    **kwargs,
):
    del sender, kwargs
    previous_status = getattr(instance, "previous_status", None)
    became_published = (
        instance.status == Assessment.Status.PUBLISHED
        and previous_status != Assessment.Status.PUBLISHED
    )
    if (created and instance.status == Assessment.Status.PUBLISHED) or became_published:
        transaction.on_commit(
            lambda: create_assessment_published_notifications(instance),
        )


@receiver(pre_save, sender=AssessmentResult)
def cache_previous_result_state(sender, instance: AssessmentResult, **kwargs):
    del sender, kwargs
    instance.previous_submission_status = None
    instance.previous_obtained_marks = None
    if instance.pk:
        previous = (
            AssessmentResult.objects.filter(pk=instance.pk)
            .values(
                "submission_status",
                "obtained_marks",
            )
            .first()
        )
        if previous is not None:
            instance.previous_submission_status = previous["submission_status"]
            instance.previous_obtained_marks = previous["obtained_marks"]


@receiver(post_save, sender=AssessmentResult)
def check_intervention_threshold(
    sender,
    instance: AssessmentResult,
    **kwargs,
):
    del sender, kwargs
    if not instance.is_below_passing:
        return

    assessment = instance.assessment
    obtained = float(instance.obtained_marks)
    passing = float(assessment.passing_marks)
    ratio = obtained / passing

    if ratio < HIGH_SEVERITY_RATIO_THRESHOLD:
        severity = InterventionLog.Severity.HIGH
    elif ratio < MEDIUM_SEVERITY_RATIO_THRESHOLD:
        severity = InterventionLog.Severity.MEDIUM
    else:
        severity = InterventionLog.Severity.LOW

    title = (
        f"Low Grade Alert: {instance.student.first_name} {instance.student.last_name} "
        f"scored {instance.obtained_marks}/{assessment.total_marks} "
        f"on '{assessment.title}'"
    )
    description = (
        f"Student obtained {instance.percentage}% "
        f"(passing threshold: {assessment.passing_marks}/{assessment.total_marks}). "
        f"Subject: {assessment.subject.name} | "
        f"Section: {assessment.section.name} | "
        f"Teacher: {assessment.teacher.user.name}"
    )

    InterventionLog.objects.get_or_create(
        student=instance.student,
        source_id=instance.id,
        defaults={
            "organization": instance.organization,
            "intervention_type": InterventionLog.InterventionType.LOW_GRADE,
            "severity": severity,
            "status": InterventionLog.Status.OPEN,
            "source_model": "assessments.AssessmentResult",
            "title": title,
            "description": description,
        },
    )


@receiver(post_save, sender=AssessmentResult)
def create_assessment_grade_notifications(
    sender,
    instance: AssessmentResult,
    created,
    **kwargs,
):
    del sender, kwargs
    previous_marks = getattr(instance, "previous_obtained_marks", None)
    previous_status = getattr(instance, "previous_submission_status", None)
    newly_graded = (previous_marks is None and instance.obtained_marks is not None) or (
        previous_status != AssessmentResult.SubmissionStatus.GRADED
        and instance.submission_status == AssessmentResult.SubmissionStatus.GRADED
    )

    if created:
        newly_graded = (
            instance.obtained_marks is not None
            or instance.submission_status == AssessmentResult.SubmissionStatus.GRADED
        )

    if newly_graded:
        transaction.on_commit(
            lambda: create_assessment_graded_notifications(instance),
        )
