from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import BaseUserManager
from django.db import models
from django.db.models import CharField
from django.db.models import DateTimeField
from django.db.models import EmailField
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from students.models import Parent
from students.models import ParentStudentLink

from core.models import TimeStampedModel
from core.models import UUIDModel


class UserManager(BaseUserManager):
    def create_user(self, email=None, password=None, **extra_fields):
        role = extra_fields.get("role")
        if not email and role != "PARENT":
            raise ValueError(_("The Email field must be set"))
        if email:
            email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(UUIDModel, TimeStampedModel, AbstractUser):
    """
    Default custom user model for core.
    """

    class Role(models.TextChoices):
        ORGANIZATION = "ORGANIZATION", _("Organization")
        BRANCH_ADMIN = "BRANCH_ADMIN", _("Branch Admin")
        TEACHER = "TEACHER", _("Teacher")
        PARENT = "PARENT", _("Parent")

    username = None
    email = EmailField(_("Email Address"), unique=True, null=True, blank=True)
    name = CharField(_("First Name"), blank=True, max_length=255)
    father_name = CharField(_("Father's Name"), blank=True, max_length=255)
    grandfather_name = CharField(_("Grandfather's Name"), blank=True, max_length=255)
    role = CharField(
        _("Role"),
        max_length=20,
        choices=Role.choices,
        blank=True,
    )
    phone_number = CharField(
        _("Phone Number"),
        null=True,
        blank=True,
        unique=True,
        max_length=20,
    )
    address = CharField(_("Address"), blank=True, max_length=255)
    verified_at = DateTimeField(_("Verified At"), blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()  # type: ignore[assignment]

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.pk})

    @property
    def children(self):
        """Returns students linked to this user as a parent."""
        return [
            link.student
            for link in ParentStudentLink.objects.filter(
                parent__user=self,
            ).select_related(
                "student",
            )
        ]

    @property
    def parent_memberships(self):
        """Returns parent profile memberships for this user."""
        try:
            return self.parent_profile
        except Parent.DoesNotExist:
            return None


class ApprovalLoginToken(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="approval_login_tokens",
        verbose_name=_("User"),
    )
    token_hash = models.CharField(_("Token Hash"), max_length=64)
    expires_at = models.DateTimeField(_("Expires At"))
    used_at = models.DateTimeField(_("Used At"), blank=True, null=True)

    class Meta:
        verbose_name = _("Approval Login Token")
        verbose_name_plural = _("Approval Login Tokens")

    def __str__(self) -> str:
        return f"Approval login token for {self.user_id}"


class ParentLoginOTP(UUIDModel, TimeStampedModel):
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="parent_login_otps",
        verbose_name=_("User"),
    )
    phone_number = models.CharField(_("Phone Number"), max_length=20)
    code_hash = models.CharField(_("Code Hash"), max_length=64)
    expires_at = models.DateTimeField(_("Expires At"))
    used_at = models.DateTimeField(_("Used At"), blank=True, null=True)
    failed_attempts = models.PositiveSmallIntegerField(
        _("Failed Attempts"),
        default=0,
    )

    class Meta:
        verbose_name = _("Parent Login OTP")
        verbose_name_plural = _("Parent Login OTPs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Parent login OTP for {self.user_id}"
