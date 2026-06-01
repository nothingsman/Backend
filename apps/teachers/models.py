from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.fields import EncryptedCharField
from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from core.models import UUIDModel


class Teacher(UUIDModel, TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
        verbose_name=_("User"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="teachers",
        verbose_name=_("Organization"),
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.CASCADE,
        related_name="teachers",
        verbose_name=_("Branch"),
    )
    employee_id = models.CharField(
        _("Employee ID"),
        max_length=50,
        unique=True,
        null=True,
        blank=True,
    )
    bio = EncryptedTextField(_("Bio"), blank=True)
    specialization = models.CharField(
        _("Specialization"),
        max_length=255,
        blank=True,
    )
    joining_date = models.DateField(_("Joining Date"), null=True, blank=True)

    class Meta:
        verbose_name = _("Teacher")
        verbose_name_plural = _("Teachers")
        unique_together = ("organization", "employee_id")

    def __str__(self):
        return f"{self.user.name} ({self.employee_id})"


class TeacherQualification(UUIDModel, TimeStampedModel):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="qualifications",
        verbose_name=_("Teacher"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="teacher_qualifications",
        verbose_name=_("Organization"),
    )
    degree_name = models.CharField(_("Degree Name"), max_length=255)
    institution = EncryptedCharField(_("Institution"), max_length=255)
    field_of_study = EncryptedCharField(_("Field of Study"), max_length=255)
    completion_date = models.DateField(_("Completion Date"))
    certificate_copy = models.ForeignKey(
        "media.MediaFile",
        verbose_name=_("Certificate Copy"),
        on_delete=models.SET_NULL,
        related_name="teacher_qualification_certificate_files",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("Teacher Qualification")
        verbose_name_plural = _("Teacher Qualifications")

    def __str__(self):
        return f"{self.teacher.employee_id} - {self.degree_name}"


class TeacherSubjectAssignment(UUIDModel, TimeStampedModel):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
        verbose_name=_("Teacher"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="teacher_subject_assignments",
        verbose_name=_("Organization"),
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        verbose_name=_("Subject"),
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        verbose_name=_("Section"),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        verbose_name=_("Academic Year"),
    )

    class Meta:
        verbose_name = _("Teacher Subject Assignment")
        verbose_name_plural = _("Teacher Subject Assignments")
        unique_together = ("teacher", "subject", "section", "academic_year")

    def __str__(self):
        return f"{self.teacher.user.name} - {self.subject.name} ({self.section.name})"


class HomeroomAssignment(UUIDModel, TimeStampedModel):
    """
    Assigns exactly one homeroom (class) teacher to a section for a given
    academic year. A section can have only one homeroom teacher per year,
    and a teacher can be homeroom for multiple sections (different grades /
    branches) if needed.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="homeroom_assignments",
        verbose_name=_("Organization"),
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.CASCADE,
        related_name="homeroom_assignments",
        verbose_name=_("Branch"),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="homeroom_assignments",
        verbose_name=_("Academic Year"),
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.PROTECT,  # prevent accidental cascade
        related_name="homeroom_assignments",
        verbose_name=_("Section"),
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,  # preserve history if teacher leaves
        related_name="homeroom_assignments",
        verbose_name=_("Homeroom Teacher"),
    )
    notes = models.TextField(_("Notes"), blank=True)

    class Meta:
        verbose_name = _("Homeroom Assignment")
        verbose_name_plural = _("Homeroom Assignments")
        # One homeroom teacher per section per academic year
        unique_together = ("section", "academic_year")
        ordering = ["-academic_year__start_date", "section__name"]

    def __str__(self):
        return (
            f"{self.section.name} | {self.academic_year.name} → "
            f"{self.teacher.user.name} ({self.teacher.employee_id})"
        )
