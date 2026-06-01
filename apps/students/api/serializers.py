from academics.models import AcademicYear
from academics.models import Section
from accounts.api.serializers import UserSerializer
from accounts.models import User
from accounts.services import consume_parent_invitation_verification_token
from accounts.services import normalize_phone_number
from branches.models import Branch
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from students.models import Parent
from students.models import ParentStudentLink
from students.models import Student
from students.models import StudentAcademicYearSection

from core.api.access import user_can_access_branch
from media.api.serializers import MediaFileReferenceField

# Base field list derived from the Student model — kept explicit so
# StudentReadSerializer can safely extend it without iterating "__all__".
STUDENT_BASE_FIELDS = [
    "id",
    "organization",
    "branch",
    "academic_year",
    "first_name",
    "last_name",
    "gender",
    "date_of_birth",
    "roll_no",
    "current_section",
    "admission_date",
    "photo",
    "status",
    "created_at",
    "updated_at",
]

PARENT_BASE_FIELDS = [
    "id",
    "user",
    "organizations",
    "branches",
    "secondary_phone_number",
    "occupation",
    "work_address",
    "relationship_notes",
    "emergency_contact_name",
    "emergency_contact_phone",
    "is_active",
    "created_at",
    "updated_at",
]


class StudentSerializer(serializers.ModelSerializer):
    """Write serializer — accepts FK ids for create / update."""

    photo = MediaFileReferenceField(
        required=False,
        allow_null=True,
        content_type_prefix="image/",
    )
    academic_year = serializers.PrimaryKeyRelatedField(
        queryset=AcademicYear.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Student
        fields = STUDENT_BASE_FIELDS
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        academic_year = attrs.get("academic_year")
        current_section = attrs.get("current_section", serializers.empty)
        instance = self.instance

        if instance is None and academic_year is None:
            raise ValidationError(
                {"academic_year": "This field is required."},
            )

        if academic_year is None and current_section is not serializers.empty:
            raise ValidationError(
                {
                    "academic_year": (
                        "This field is required when setting current_section."
                    ),
                },
            )

        if academic_year is None:
            return attrs

        organization = attrs.get(
            "organization",
            getattr(instance, "organization", None),
        )
        branch = attrs.get("branch", getattr(instance, "branch", None))

        if (
            organization is not None
            and academic_year.organization_id != organization.id
        ):
            raise ValidationError(
                {
                    "academic_year": (
                        "Academic year must belong to the selected organization."
                    ),
                },
            )

        if branch is not None and academic_year.branch_id != branch.id:
            raise ValidationError(
                {
                    "academic_year": (
                        "Academic year must belong to the selected branch."
                    ),
                },
            )

        if current_section is serializers.empty or current_section is None:
            return attrs

        if current_section.academic_year_id != academic_year.id:
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to the selected academic year."
                    ),
                },
            )

        if branch is not None and current_section.branch_id != branch.id:
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to the selected branch."
                    ),
                },
            )

        if (
            organization is not None
            and current_section.organization_id != organization.id
        ):
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to the selected organization."
                    ),
                },
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        academic_year = validated_data.pop("academic_year")
        section = validated_data.pop("current_section", None)
        if academic_year.is_current:
            validated_data["current_section"] = section
        else:
            validated_data["current_section"] = None
        student = super().create(validated_data)
        self._upsert_academic_year_section(
            student=student,
            academic_year=academic_year,
            section=section,
        )
        return student

    @transaction.atomic
    def update(self, instance, validated_data):
        academic_year = validated_data.pop("academic_year", None)
        section = validated_data.pop("current_section", serializers.empty)
        if academic_year is not None and section is not serializers.empty:
            if academic_year.is_current:
                validated_data["current_section"] = section
        elif academic_year is None and section is not serializers.empty:
            raise ValidationError(
                {
                    "academic_year": (
                        "This field is required when setting current_section."
                    ),
                },
            )

        student = super().update(instance, validated_data)

        if academic_year is not None:
            if section is serializers.empty:
                existing_assignment = student.academic_year_sections.filter(
                    academic_year=academic_year,
                ).first()
                section = (
                    existing_assignment.section
                    if existing_assignment is not None
                    else None
                )
            self._upsert_academic_year_section(
                student=student,
                academic_year=academic_year,
                section=section,
                update_section=section is not serializers.empty,
            )

        return student

    def _upsert_academic_year_section(
        self,
        *,
        student: Student,
        academic_year: AcademicYear,
        section,
        update_section: bool = True,
    ) -> None:
        assignment, created = StudentAcademicYearSection.objects.get_or_create(
            student=student,
            academic_year=academic_year,
            defaults={"section": section},
        )
        if not created and update_section:
            assignment.section = section
            assignment.full_clean()
            assignment.save(update_fields=["section", "updated_at"])
        elif created:
            assignment.full_clean()
            assignment.save()

        student.sync_current_section_from_academic_year(academic_year)


class StudentReadSerializer(StudentSerializer):
    """
    Read serializer — all student fields plus human-readable details for
    every related object so callers never need a follow-up request.
    """

    # Section
    section_name = serializers.SerializerMethodField()

    # Grade (via section)
    grade_id = serializers.SerializerMethodField()
    grade_name = serializers.SerializerMethodField()
    grade_level = serializers.SerializerMethodField()

    # Academic year attached to the section (nullable on Section)
    academic_year_id = serializers.SerializerMethodField()
    academic_year_name = serializers.SerializerMethodField()

    # Branch
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    # Organization
    organization_name = serializers.CharField(
        source="organization.name",
        read_only=True,
    )
    parent_details = serializers.SerializerMethodField()

    class Meta(StudentSerializer.Meta):
        fields = [
            *(field for field in STUDENT_BASE_FIELDS if field != "academic_year"),
            "section_name",
            "grade_id",
            "grade_name",
            "grade_level",
            "academic_year_id",
            "academic_year_name",
            "branch_name",
            "organization_name",
            "parent_details",
        ]

    @staticmethod
    def _format_parent_full_name(parent: Parent) -> str:
        user = parent.user
        return " ".join(
            part
            for part in [user.name, user.father_name, user.grandfather_name]
            if part
        )

    def _get_requested_assignment(self, obj) -> StudentAcademicYearSection | None:
        request = self.context.get("request")
        if request is None:
            return None

        academic_year_id = request.query_params.get("academic_year")
        if not academic_year_id:
            return None

        prefetched_assignments = getattr(obj, "filtered_academic_year_sections", None)
        if prefetched_assignments is not None:
            return prefetched_assignments[0] if prefetched_assignments else None

        return (
            obj.academic_year_sections.select_related(
                "section__grade",
                "academic_year",
            )
            .filter(academic_year_id=academic_year_id)
            .first()
        )

    def _get_section_for_response(self, obj):
        assignment = self._get_requested_assignment(obj)
        if assignment is not None:
            return assignment.section
        return obj.current_section

    def _get_academic_year_for_response(self, obj) -> AcademicYear | None:
        assignment = self._get_requested_assignment(obj)
        if assignment is not None:
            return assignment.academic_year

        section = obj.current_section
        if section is None:
            return None
        return section.academic_year

    def get_section_name(self, obj) -> str | None:
        section = self._get_section_for_response(obj)
        return section.name if section else None

    def get_grade_id(self, obj) -> str | None:
        section = self._get_section_for_response(obj)
        if section is None:
            return None
        return str(section.grade_id)

    def get_grade_name(self, obj) -> str | None:
        section = self._get_section_for_response(obj)
        if section is None:
            return None
        return section.grade.name

    def get_grade_level(self, obj) -> int | None:
        section = self._get_section_for_response(obj)
        if section is None:
            return None
        return section.grade.level

    def get_academic_year_id(self, obj) -> str | None:
        academic_year = self._get_academic_year_for_response(obj)
        return str(academic_year.id) if academic_year else None

    def get_academic_year_name(self, obj) -> str | None:
        academic_year = self._get_academic_year_for_response(obj)
        return academic_year.name if academic_year else None

    def get_parent_details(self, obj) -> list[dict[str, str | bool | None]]:
        parent_links = getattr(obj, "prefetched_parent_links", None)
        if parent_links is None:
            parent_links = obj.parent_links.select_related("parent__user")

        return [
            {
                "id": str(link.parent_id),
                "user": str(link.parent.user_id),
                "full_name": self._format_parent_full_name(link.parent),
                "relationship_type": link.relationship_type,
                "is_primary_contact": link.is_primary_contact,
            }
            for link in parent_links
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        assignment = self._get_requested_assignment(instance)
        if assignment is not None:
            data["current_section"] = (
                str(assignment.section_id) if assignment.section_id else None
            )
        return data


class ParentSerializer(serializers.ModelSerializer):
    """Write serializer for parent profiles."""

    organization_ids = serializers.SerializerMethodField()
    branch_ids = serializers.SerializerMethodField()

    class Meta:
        model = Parent
        fields = [
            *PARENT_BASE_FIELDS,
            "organization_ids",
            "branch_ids",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    @staticmethod
    def _extract_input_values(data, field_name: str):
        if hasattr(data, "getlist"):
            values = data.getlist(field_name)
            if values:
                return values
        return data.get(field_name)

    @staticmethod
    def _normalize_input_values(values) -> list[str]:
        if values is None:
            return []
        if isinstance(values, (list, tuple)):
            return [str(value) for value in values]
        return [str(values)]

    def to_internal_value(self, data):
        incoming_data = data.copy()
        alias_map = {
            "organization_ids": "organizations",
            "branch_ids": "branches",
        }

        for alias, canonical in alias_map.items():
            alias_values = self._extract_input_values(data, alias)
            canonical_values = self._extract_input_values(data, canonical)

            if alias_values is None:
                continue

            if canonical_values is not None:
                normalized_aliases = self._normalize_input_values(alias_values)
                normalized_canonical = self._normalize_input_values(canonical_values)
                if normalized_aliases != normalized_canonical:
                    raise ValidationError(
                        {
                            alias: (
                                f"{alias} must match {canonical} when both are "
                                "provided."
                            ),
                        },
                    )
                continue

            if hasattr(incoming_data, "setlist"):
                incoming_data.setlist(alias, [])
                incoming_data.setlist(
                    canonical,
                    self._normalize_input_values(alias_values),
                )
            else:
                incoming_data[canonical] = alias_values

        return super().to_internal_value(incoming_data)

    def get_organization_ids(self, obj) -> list[str]:
        return [str(organization.id) for organization in obj.organizations.all()]

    def get_branch_ids(self, obj) -> list[str]:
        return [str(branch.id) for branch in obj.branches.all()]

    def validate(self, attrs):
        user = attrs.get("user", getattr(self.instance, "user", None))
        organizations = attrs.get("organizations")
        branches = attrs.get("branches")

        if user and getattr(user, "role", "") != user.Role.PARENT:
            attrs["user"].role = user.Role.PARENT

        if self.instance is not None and organizations is None:
            organizations = self.instance.organizations.all()
        if self.instance is not None and branches is None:
            branches = self.instance.branches.all()

        if organizations is not None and branches is not None:
            organization_ids = {organization.id for organization in organizations}
            invalid_branch = next(
                (
                    branch
                    for branch in branches
                    if branch.organization_id not in organization_ids
                ),
                None,
            )
            if invalid_branch is not None:
                raise ValidationError(
                    {
                        "branches": (
                            "Every assigned branch must belong to one of the "
                            "selected organizations."
                        ),
                    },
                )

        return attrs

    def create(self, validated_data):
        organizations = validated_data.pop("organizations", [])
        branches = validated_data.pop("branches", [])
        user = validated_data["user"]
        user.role = user.Role.PARENT
        user.save(update_fields=["role"])
        parent = Parent.objects.create(**validated_data)
        parent.organizations.set(organizations)
        parent.branches.set(branches)
        parent.full_clean()
        return parent

    def update(self, instance, validated_data):
        organizations = validated_data.pop("organizations", None)
        branches = validated_data.pop("branches", None)

        user = validated_data.get("user")
        if user is not None and user.role != user.Role.PARENT:
            user.role = user.Role.PARENT
            user.save(update_fields=["role"])

        instance = super().update(instance, validated_data)
        if organizations is not None:
            instance.organizations.set(organizations)
        if branches is not None:
            instance.branches.set(branches)
        instance.full_clean()
        return instance


class ParentReadSerializer(ParentSerializer):
    """Read serializer with user, organization, branch, and student details."""

    user_details = UserSerializer(source="user", read_only=True)
    organization_details = serializers.SerializerMethodField()
    branch_details = serializers.SerializerMethodField()
    student_details = serializers.SerializerMethodField()

    class Meta(ParentSerializer.Meta):
        fields = [
            *ParentSerializer.Meta.fields,
            "user_details",
            "organization_details",
            "branch_details",
            "student_details",
        ]

    def _request_user_can_view_phone_numbers(self, obj: Parent) -> bool:
        request = self.context.get("request")
        if request is None:
            return True

        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False

        if user.is_superuser or obj.user_id == user.id:
            return True

        if obj.organizations.filter(owner=user).exists():
            return True

        if obj.branches.filter(
            admins__user=user,
            admins__status="ACTIVE",
        ).exists():
            return True

        return obj.student_links.filter(
            student__current_section__homeroom_assignments__teacher__user=user,
        ).exists()

    def get_organization_details(self, obj) -> list[dict]:
        return [
            {
                "id": str(organization.id),
                "name": organization.name,
                "status": organization.status,
            }
            for organization in obj.organizations.all()
        ]

    def get_branch_details(self, obj) -> list[dict]:
        return [
            {
                "id": str(branch.id),
                "name": branch.name,
                "organization": str(branch.organization_id),
                "status": branch.status,
            }
            for branch in obj.branches.all()
        ]

    def get_student_details(self, obj) -> list[dict]:
        return [
            {
                "id": str(link.student.id),
                "first_name": link.student.first_name,
                "last_name": link.student.last_name,
                "roll_no": link.student.roll_no,
                "branch": str(link.student.branch_id),
                "organization": str(link.student.organization_id),
                "relationship_type": link.relationship_type,
                "is_primary_contact": link.is_primary_contact,
            }
            for link in obj.student_links.select_related("student")
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self._request_user_can_view_phone_numbers(instance):
            return data

        user_details = data.get("user_details")
        if isinstance(user_details, dict):
            user_details["phone_number"] = None

        data["secondary_phone_number"] = None
        data["emergency_contact_phone"] = None
        return data


class ParentInviteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    father_name = serializers.CharField(max_length=255)
    grandfather_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    secondary_phone_number = serializers.CharField(
        max_length=20,
        required=False,
        default="",
        allow_blank=True,
    )
    occupation = serializers.CharField(
        max_length=255,
        required=False,
        default="",
        allow_blank=True,
    )
    work_address = serializers.CharField(
        max_length=255,
        required=False,
        default="",
        allow_blank=True,
    )
    relationship_notes = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
    )
    emergency_contact_name = serializers.CharField(
        max_length=255,
        required=False,
        default="",
        allow_blank=True,
    )
    emergency_contact_phone = serializers.CharField(
        max_length=50,
        required=False,
        default="",
        allow_blank=True,
    )

    PHONE_VALIDATION_ERROR_MESSAGE = "A parent with this phone number already exists."

    @staticmethod
    def _normalize_optional_phone(attrs: dict, field_name: str) -> None:
        value = attrs.get(field_name, "")
        if not value:
            return
        try:
            attrs[field_name] = normalize_phone_number(value)
        except ValueError as err:
            raise ValidationError({field_name: str(err)}) from err

    def _validate_existing_user(self, attrs: dict) -> User | None:
        existing_user = User.objects.filter(phone_number=attrs["phone_number"]).first()
        if existing_user is None:
            return None

        if existing_user.role != User.Role.PARENT or existing_user.is_active:
            raise ValidationError({"phone_number": self.PHONE_VALIDATION_ERROR_MESSAGE})
        if not Parent.objects.filter(user=existing_user).exists():
            raise ValidationError({"phone_number": self.PHONE_VALIDATION_ERROR_MESSAGE})
        attrs["existing_user"] = existing_user
        return existing_user

    @staticmethod
    def _validate_email_conflict(email: str, existing_user: User | None) -> None:
        if not email:
            return
        email_conflict = User.objects.filter(email__iexact=email)
        if existing_user is not None:
            email_conflict = email_conflict.exclude(pk=existing_user.pk)
        if email_conflict.exists():
            raise ValidationError(
                {"email": "A user with this email already exists."},
            )

    def validate(self, attrs):
        request = self.context.get("request")
        branch = attrs["branch"]

        try:
            attrs["phone_number"] = normalize_phone_number(attrs["phone_number"])
        except ValueError as err:
            raise ValidationError({"phone_number": str(err)}) from err

        self._normalize_optional_phone(attrs, "secondary_phone_number")
        self._normalize_optional_phone(attrs, "emergency_contact_phone")
        existing_user = self._validate_existing_user(attrs)

        email = attrs.get("email", "").strip()
        attrs["email"] = email
        self._validate_email_conflict(email, existing_user)

        if request and not user_can_access_branch(request.user, branch):
            raise ValidationError(
                {"branch": "You can only manage branches in your organizations."},
            )

        return attrs


class ParentInvitationTokenSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate_uid(self, value: str) -> str:
        try:
            user_id = force_str(urlsafe_base64_decode(value))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as err:
            message = "Invalid user ID."
            raise ValidationError(message) from err

        self.context["target_user"] = user
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context.get("target_user")

        if user is None:
            raise ValidationError({"uid": "Invalid user ID."})

        if user.role != User.Role.PARENT or user.is_active:
            raise ValidationError({"uid": "Invalid or expired invitation."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise ValidationError({"token": "Invalid or expired token."})

        try:
            parent_profile = user.parent_profile
        except Parent.DoesNotExist as err:
            raise ValidationError({"uid": "Invalid or expired invitation."}) from err

        if parent_profile.is_active:
            raise ValidationError({"uid": "Invalid or expired invitation."})

        self.context["target_parent_profile"] = parent_profile
        return attrs


class ParentInvitationOtpRequestSerializer(ParentInvitationTokenSerializer):
    pass


class ParentInvitationOtpVerifySerializer(ParentInvitationTokenSerializer):
    otp_code = serializers.RegexField(r"^\d{6}$")


class ParentCompleteInvitationSerializer(ParentInvitationTokenSerializer):
    invitation_verification_token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context["target_user"]

        try:
            consume_parent_invitation_verification_token(
                user=user,
                raw_token=attrs["invitation_verification_token"],
            )
        except signing.SignatureExpired as err:
            raise ValidationError(
                {
                    "invitation_verification_token": (
                        "Invitation verification expired. Request a new OTP."
                    ),
                },
            ) from err
        except signing.BadSignature as err:
            raise ValidationError(
                {
                    "invitation_verification_token": (
                        "Invalid invitation verification token."
                    ),
                },
            ) from err

        try:
            validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as err:
            raise ValidationError({"new_password": list(err.messages)}) from err

        return attrs


# ---------------------------------------------------------------------------
# ParentStudentLink
# ---------------------------------------------------------------------------


class ParentStudentLinkSerializer(serializers.ModelSerializer):
    """Base serializer for ParentStudentLink."""

    class Meta:
        model = ParentStudentLink
        fields = [
            "id",
            "student",
            "parent",
            "relationship_type",
            "is_primary_contact",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        parent = attrs.get("parent", getattr(self.instance, "parent", None))

        if student is None or parent is None:
            return attrs

        if not parent.organizations.filter(id=student.organization_id).exists():
            raise ValidationError(
                {
                    "parent": (
                        "The selected parent must belong to the student's organization."
                    ),
                },
            )

        if not parent.branches.filter(id=student.branch_id).exists():
            raise ValidationError(
                {
                    "parent": (
                        "The selected parent must belong to the student's branch."
                    ),
                },
            )

        return attrs


class ParentStudentLinkReadSerializer(ParentStudentLinkSerializer):
    """Serializer for reading ParentStudentLink with nested details."""

    student_details = StudentReadSerializer(source="student", read_only=True)
    parent_details = ParentReadSerializer(source="parent", read_only=True)

    class Meta(ParentStudentLinkSerializer.Meta):
        fields = [
            *ParentStudentLinkSerializer.Meta.fields,
            "student_details",
            "parent_details",
        ]


class BulkImportSerializer(serializers.Serializer):
    file = MediaFileReferenceField()
    organization = serializers.UUIDField()
    branch = serializers.UUIDField()
    current_section = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current_section = attrs.get("current_section")
        organization_id = attrs.get("organization")
        branch_id = attrs.get("branch")

        if current_section is None:
            return attrs

        if current_section.branch_id != branch_id:
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to the selected branch."
                    ),
                },
            )

        if current_section.organization_id != organization_id:
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to the selected organization."
                    ),
                },
            )

        if current_section.academic_year_id is None:
            raise ValidationError(
                {
                    "current_section": (
                        "Current section must belong to an academic year."
                    ),
                },
            )

        return attrs
