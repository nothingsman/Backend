from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.models import UUIDModel


class StudentInsight(UUIDModel, TimeStampedModel):
    class SourceEventType(models.TextChoices):
        ASSESSMENT_RESULT = "ASSESSMENT_RESULT", _("Assessment Result")
        ATTENDANCE = "ATTENDANCE", _("Attendance")
        ATTENDANCE_REASON = "ATTENDANCE_REASON", _("Attendance Reason")
        CHAT_MESSAGE = "CHAT_MESSAGE", _("Chat Message")

    class RiskBand(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")

    class Category(models.TextChoices):
        ACADEMICS = "ACADEMICS", _("Academics")
        ATTENDANCE = "ATTENDANCE", _("Attendance")
        ENGAGEMENT = "ENGAGEMENT", _("Engagement")
        COMMUNICATION = "COMMUNICATION", _("Communication")

    class SafetyStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        APPROVED = "APPROVED", _("Approved")
        FALLBACK = "FALLBACK", _("Fallback")
        REJECTED = "REJECTED", _("Rejected")

    class DeliveryStatus(models.TextChoices):
        PENDING = "PENDING", _("Pending")
        DELIVERED = "DELIVERED", _("Delivered")
        SUPPRESSED = "SUPPRESSED", _("Suppressed")
        FAILED = "FAILED", _("Failed")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="student_insights",
        verbose_name=_("Organization"),
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.CASCADE,
        related_name="student_insights",
        verbose_name=_("Branch"),
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="student_insights",
        verbose_name=_("Student"),
    )
    intervention_log = models.ForeignKey(
        "analytics.InterventionLog",
        on_delete=models.SET_NULL,
        related_name="student_insights",
        null=True,
        blank=True,
        verbose_name=_("Intervention Log"),
    )
    source_event_type = models.CharField(
        _("Source Event Type"),
        max_length=32,
        choices=SourceEventType.choices,
    )
    source_model = models.CharField(_("Source Model"), max_length=100)
    source_id = models.UUIDField(_("Source ID"), null=True, blank=True)
    dedupe_key = models.CharField(_("Dedupe Key"), max_length=255, db_index=True)
    category = models.CharField(
        _("Category"),
        max_length=20,
        choices=Category.choices,
    )
    risk_band = models.CharField(
        _("Risk Band"),
        max_length=10,
        choices=RiskBand.choices,
    )
    title = models.CharField(_("Title"), max_length=255)
    message = models.TextField(_("Message"), blank=True)
    confidence_label = models.CharField(_("Confidence Label"), max_length=20, blank=True)
    recommended_actions = models.JSONField(_("Recommended Actions"), default=list, blank=True)
    evidence = models.JSONField(_("Evidence"), default=dict, blank=True)
    model_input_summary = models.JSONField(_("Model Input Summary"), default=dict, blank=True)
    model_output = models.JSONField(_("Model Output"), default=dict, blank=True)
    safety_status = models.CharField(
        _("Safety Status"),
        max_length=15,
        choices=SafetyStatus.choices,
        default=SafetyStatus.PENDING,
    )
    safety_notes = models.JSONField(_("Safety Notes"), default=list, blank=True)
    delivery_status = models.CharField(
        _("Delivery Status"),
        max_length=15,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    delivered_at = models.DateTimeField(_("Delivered At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Student Insight")
        verbose_name_plural = _("Student Insights")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "student", "category"]),
            models.Index(fields=["student", "risk_band", "created_at"]),
            models.Index(fields=["delivery_status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.student_id} {self.category} {self.risk_band}"

