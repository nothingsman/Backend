import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import TimeStampedModel
from core.models import UUIDModel


class Attendance(UUIDModel, TimeStampedModel):
    """
    One record per student per day per section.

    Unique constraint: (student, date, section) — prevents duplicate
    submissions and is idempotent-safe for offline/PWA re-syncs when
    paired with client_side_id.
    """

    class Status(models.TextChoices):
        PRESENT = "PRESENT", _("Present")
        ABSENT = "ABSENT", _("Absent")
        LATE = "LATE", _("Late")
        EXCUSED = "EXCUSED", _("Excused")

    # ── Tenant isolation ────────────────────────────────────────────────
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("Organization"),
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("Branch"),
    )

    # ── Core references ─────────────────────────────────────────────────
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("Academic Year"),
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("Section"),
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
        verbose_name=_("Student"),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="recorded_attendance",
        verbose_name=_("Recorded By"),
    )

    # ── Attendance data ──────────────────────────────────────────────────
    date = models.DateField(_("Date"))
    status = models.CharField(
        _("Status"),
        max_length=10,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    remarks = models.TextField(_("Remarks"), blank=True)

    # ── PWA / Offline support ───────────────────────────────────────────
    client_side_id = models.UUIDField(
        _("Client-Side ID"),
        default=uuid.uuid4,
        unique=True,
        help_text=_(
            "UUID generated on the client for idempotent offline sync. "
            "If a record with this ID already exists, the server will "
            "return the existing record instead of creating a duplicate.",
        ),
    )

    class Meta:
        verbose_name = _("Attendance")
        verbose_name_plural = _("Attendance Records")
        unique_together = ("student", "date", "section")
        ordering = ["-date", "section__name", "student__roll_no"]
        indexes = [
            models.Index(fields=["organization", "branch", "date"]),
            models.Index(fields=["student", "academic_year"]),
            models.Index(fields=["section", "date"]),
        ]

    def __str__(self):
        return (
            f"{self.student} | {self.date} | "
            f"{self.get_status_display()} ({self.section.name})"
        )

    @property
    def needs_reason(self):
        """True when status warrants a parent explanation."""
        return self.status in (
            self.Status.ABSENT,
            self.Status.LATE,
            self.Status.EXCUSED,
        )


class AttendanceReason(UUIDModel, TimeStampedModel):
    """
    Intervention hook — lets a parent (or admin) attach a structured
    reason to any non-PRESENT attendance record.
    """

    class Category(models.TextChoices):
        SICKNESS = "SICKNESS", _("Sickness")
        TRANSPORTATION = "TRANSPORTATION", _("Transportation Issue")
        FAMILY_ISSUE = "FAMILY_ISSUE", _("Family Issue")
        EMERGENCY = "EMERGENCY", _("Emergency")
        RELIGIOUS = "RELIGIOUS", _("Religious Observance")
        BEREAVEMENT = "BEREAVEMENT", _("Bereavement")
        UNKNOWN = "UNKNOWN", _("Unknown")
        OTHER = "OTHER", _("Other")

    # ── Tenant isolation ────────────────────────────────────────────────
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="attendance_reasons",
        verbose_name=_("Organization"),
    )

    # ── Link to the attendance record ────────────────────────────────────
    attendance = models.OneToOneField(
        Attendance,
        on_delete=models.CASCADE,
        related_name="reason",
        verbose_name=_("Attendance Record"),
    )

    # ── Parent's input ───────────────────────────────────────────────────
    reason_category = models.CharField(
        _("Reason Category"),
        max_length=20,
        choices=Category.choices,
        default=Category.UNKNOWN,
    )
    note = models.TextField(
        _("Parent Note"),
        blank=True,
        help_text=_("Free-text explanation from the parent."),
    )
    parent_confirmed = models.BooleanField(
        _("Parent Confirmed"),
        default=False,
        help_text=_(
            "Set to True once the parent has acknowledged and explained the absence.",
        ),
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_attendance_reasons",
        verbose_name=_("Confirmed By"),
    )
    confirmed_at = models.DateTimeField(_("Confirmed At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Attendance Reason")
        verbose_name_plural = _("Attendance Reasons")

    def __str__(self):
        return (
            f"{self.attendance.student} | {self.attendance.date} | "
            f"{self.get_reason_category_display()}"
        )


class AttendanceSummary(UUIDModel, TimeStampedModel):
    """
    Aggregated attendance statistics per student per academic year.

    Updated by a Celery task (or signal) after every attendance save so
    analytics queries hit this table instead of scanning all records.
    """

    # ── Tenant isolation ────────────────────────────────────────────────
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
        verbose_name=_("Organization"),
    )

    # ── References ──────────────────────────────────────────────────────
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
        verbose_name=_("Student"),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="attendance_summaries",
        verbose_name=_("Academic Year"),
    )

    # ── Aggregated counters ──────────────────────────────────────────────
    total_present = models.PositiveIntegerField(_("Total Present"), default=0)
    total_absent = models.PositiveIntegerField(_("Total Absent"), default=0)
    total_late = models.PositiveIntegerField(_("Total Late"), default=0)
    total_excused = models.PositiveIntegerField(_("Total Excused"), default=0)
    total_school_days = models.PositiveIntegerField(_("Total School Days"), default=0)

    last_updated = models.DateTimeField(_("Last Updated"), auto_now=True)

    class Meta:
        verbose_name = _("Attendance Summary")
        verbose_name_plural = _("Attendance Summaries")
        unique_together = ("student", "academic_year")
        ordering = ["-academic_year__start_date"]

    def __str__(self):
        return f"{self.student} | {self.academic_year.name} Summary"

    @property
    def attendance_rate(self):
        """Percentage of days present (including excused as present)."""
        total = self.total_school_days
        if total == 0:
            return 0.0
        return round((self.total_present + self.total_excused) / total * 100, 2)
