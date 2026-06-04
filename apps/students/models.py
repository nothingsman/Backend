from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.fields import EncryptedCharField
from core.fields import EncryptedDateField
from core.fields import EncryptedTextField
from core.models import TimeStampedModel
from core.models import UUIDModel


class Parent(UUIDModel, TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_profile",
        verbose_name=_("User"),
    )
    organizations = models.ManyToManyField(
        "organizations.Organization",
        related_name="parents",
        verbose_name=_("Organizations"),
        blank=True,
    )
    branches = models.ManyToManyField(
        "branches.Branch",
        related_name="parents",
        verbose_name=_("Branches"),
        blank=True,
    )
    secondary_phone_number = EncryptedCharField(
        _("Secondary Phone Number"),
        max_length=20,
        blank=True,
    )
    occupation = EncryptedCharField(_("Occupation"), max_length=255, blank=True)
    work_address = EncryptedCharField(_("Work Address"), max_length=255, blank=True)
    relationship_notes = EncryptedTextField(_("Relationship Notes"), blank=True)
    emergency_contact_name = EncryptedCharField(
        _("Emergency Contact Name"),
        max_length=255,
        blank=True,
    )
    emergency_contact_phone = EncryptedCharField(
        _("Emergency Contact Phone"),
        max_length=50,
        blank=True,
    )
    is_active = models.BooleanField(_("Is Active"), default=True)

    class Meta:
        verbose_name = _("Parent")
        verbose_name_plural = _("Parents")
        ordering = ["-created_at"]

    def __str__(self):
        return self.user.name or self.user.email

    def clean(self):
        super().clean()

        if not self.pk:
            return

        organization_ids = set(
            self.organizations.values_list("id", flat=True),
        )
        invalid_branch = self.branches.exclude(
            organization_id__in=organization_ids,
        ).first()
        if invalid_branch is not None:
            raise ValidationError(
                {
                    "branches": _(
                        "Every assigned branch must belong to one of the "
                        "parent's organizations.",
                    ),
                },
            )


class Student(UUIDModel, TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "MALE", _("Male")
        FEMALE = "FEMALE", _("Female")
        OTHER = "OTHER", _("Other")

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", _("Active")
        INACTIVE = "INACTIVE", _("Inactive")
        WITHDRAWN = "WITHDRAWN", _("Withdrawn")
        GRADUATED = "GRADUATED", _("Graduated")

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="students",
        verbose_name=_("Organization"),
    )
    branch = models.ForeignKey(
        "branches.Branch",
        on_delete=models.CASCADE,
        related_name="students",
        verbose_name=_("Branch"),
    )
    first_name = EncryptedCharField(_("First Name"), max_length=255)
    last_name = EncryptedCharField(_("Last Name"), max_length=255)
    gender = models.CharField(_("Gender"), max_length=10, choices=Gender.choices)
    date_of_birth = EncryptedDateField(_("Date of Birth"))
    roll_no = models.CharField(_("Roll Number"), max_length=50, default="", blank=True)
    current_section = models.ForeignKey(
        "academics.Section",
        on_delete=models.PROTECT,
        related_name="students",
        verbose_name=_("Current Section"),
        null=True,
        blank=True,
    )
    admission_date = models.DateField(_("Admission Date"), null=True, blank=True)
    photo = models.ForeignKey(
        "media.MediaFile",
        verbose_name=_("Photo"),
        on_delete=models.SET_NULL,
        related_name="student_photo_files",
        blank=True,
        null=True,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        verbose_name = _("Student")
        verbose_name_plural = _("Students")
        unique_together = ("branch", "current_section", "roll_no")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.roll_no})"

    def sync_current_section_from_academic_year(self, academic_year) -> None:
        if not academic_year.is_current:
            return

        self.current_section_id = (
            self.academic_year_sections.filter(academic_year=academic_year)
            .values_list("section", flat=True)
            .first()
        )
        self.save(update_fields=["current_section", "updated_at"])

    @property
    def parents(self):
        """Returns parent profiles linked to this student."""
        return [
            link.parent
            for link in ParentStudentLink.objects.filter(student=self).select_related(
                "parent__user",
            )
        ]


class StudentAcademicYearSection(UUIDModel, TimeStampedModel):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="academic_year_sections",
        verbose_name=_("Student"),
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.CASCADE,
        related_name="student_sections",
        verbose_name=_("Academic Year"),
    )
    section = models.ForeignKey(
        "academics.Section",
        on_delete=models.PROTECT,
        related_name="student_academic_year_sections",
        verbose_name=_("Section"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Student Academic Year Section")
        verbose_name_plural = _("Student Academic Year Sections")
        unique_together = ("student", "academic_year")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} - {self.academic_year}"

    def clean(self):
        super().clean()

        if not self.student_id or not self.academic_year_id:
            return

        errors: dict[str, str] = {}

        if self.academic_year.branch_id != self.student.branch_id:
            errors["academic_year"] = _(
                "Academic year must belong to the student's branch.",
            )

        if self.academic_year.organization_id != self.student.organization_id:
            errors["academic_year"] = _(
                "Academic year must belong to the student's organization.",
            )

        if self.section_id is None:
            if errors:
                raise ValidationError(errors)
            return

        if self.section.branch_id != self.student.branch_id:
            errors["section"] = _("Section must belong to the student's branch.")

        if self.section.organization_id != self.student.organization_id:
            errors["section"] = _(
                "Section must belong to the student's organization.",
            )

        if self.section.academic_year_id != self.academic_year_id:
            errors["section"] = _(
                "Section must belong to the selected academic year.",
            )

        if errors:
            raise ValidationError(errors)


class ParentStudentLink(UUIDModel, TimeStampedModel):
    class Relationship(models.TextChoices):
        FATHER = "FATHER", _("Father")
        MOTHER = "MOTHER", _("Mother")
        GUARDIAN = "GUARDIAN", _("Guardian")
        OTHER = "OTHER", _("Other")

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    parent = models.ForeignKey(
        Parent,
        on_delete=models.CASCADE,
        related_name="student_links",
        verbose_name=_("Parent"),
    )
    relationship_type = models.CharField(
        _("Relationship Type"),
        max_length=20,
        choices=Relationship.choices,
    )
    is_primary_contact = models.BooleanField(_("Is Primary Contact"), default=False)

    class Meta:
        verbose_name = _("Parent Student Link")
        verbose_name_plural = _("Parent Student Links")
        unique_together = ("student", "parent")
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.parent.user.name} - "
            f"{self.student.first_name} ({self.relationship_type})"
        )

    def clean(self):
        super().clean()

        if not self.student_id or not self.parent_id:
            return

        if not self.parent.organizations.filter(
            id=self.student.organization_id,
        ).exists():
            raise ValidationError(
                {
                    "parent": _(
                        "The selected parent must belong to the student's "
                        "organization.",
                    ),
                },
            )

        if not self.parent.branches.filter(id=self.student.branch_id).exists():
            raise ValidationError(
                {
                    "parent": _(
                        "The selected parent must belong to the student's branch.",
                    ),
                },
            )


class StudentBehaviourIncident(UUIDModel, TimeStampedModel):
    class Severity(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="behaviour_incidents",
        verbose_name=_("Student"),
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="student_behaviour_incidents",
        verbose_name=_("Teacher"),
        null=True,
        blank=True,
    )
    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"))
    severity = models.CharField(
        _("Severity"),
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
    )
    occurred_at = models.DateTimeField(_("Occurred At"))
    source = models.CharField(_("Source"), max_length=100, default="Teacher Incident")

    class Meta:
        verbose_name = _("Student Behaviour Incident")
        verbose_name_plural = _("Student Behaviour Incidents")
        ordering = ["-occurred_at", "-created_at"]

    def __str__(self):
        return f"{self.student} - {self.title}"


class StudentBehaviourRemark(UUIDModel, TimeStampedModel):
    class Severity(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MEDIUM", _("Medium")
        HIGH = "HIGH", _("High")

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="behaviour_remarks",
        verbose_name=_("Student"),
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="student_behaviour_remarks",
        verbose_name=_("Teacher"),
        null=True,
        blank=True,
    )
    title = models.CharField(_("Title"), max_length=255)
    description = models.TextField(_("Description"))
    severity = models.CharField(
        _("Severity"),
        max_length=20,
        choices=Severity.choices,
        default=Severity.LOW,
    )
    occurred_at = models.DateTimeField(_("Occurred At"))
    source = models.CharField(_("Source"), max_length=100, default="Teacher Remark")

    class Meta:
        verbose_name = _("Student Behaviour Remark")
        verbose_name_plural = _("Student Behaviour Remarks")
        ordering = ["-occurred_at", "-created_at"]

    def __str__(self):
        return f"{self.student} - {self.title}"
