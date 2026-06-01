from accounts.models import User
from branches.models import Branch
from branches.models import BranchAdmin
from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "organization",
            "school",
            "name",
            "address",
            "city",
            "region",
            "contact_phone",
            "contact_email",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        organization = attrs.get(
            "organization",
            getattr(self.instance, "organization", None),
        )
        school = attrs.get("school", getattr(self.instance, "school", None))

        if request is None:
            return attrs

        if organization is not None and organization.owner_id != request.user.id:
            raise ValidationError(
                {"organization": "You can only manage your own organizations."},
            )

        if school is not None and school.organization.owner_id != request.user.id:
            raise ValidationError(
                {"school": "You can only manage schools in your organizations."},
            )

        if (
            organization is not None
            and school is not None
            and school.organization_id != organization.id
        ):
            raise ValidationError(
                {
                    "school": "Selected school does not belong to the selected organization.",  # noqa: E501
                },
            )

        return attrs


class BranchAdminSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = BranchAdmin
        fields = [
            "id",
            "organization",
            "branch",
            "user",
            "email",
            "name",
            "emergency_contact_name",
            "emergency_contact_phone",
            "role_title",
            "qualification",
            "status",
            "last_login",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_login"]

    def validate(self, attrs):
        request = self.context.get("request")
        organization = attrs.get(
            "organization",
            getattr(self.instance, "organization", None),
        )
        branch = attrs.get("branch", getattr(self.instance, "branch", None))

        if request is None:
            return attrs

        if organization is not None and organization.owner_id != request.user.id:
            raise ValidationError(
                {"organization": "You can only manage your own organizations."},
            )

        if branch is not None and branch.organization.owner_id != request.user.id:
            raise ValidationError(
                {"branch": "You can only manage branches in your organizations."},
            )

        if (
            organization is not None
            and branch is not None
            and branch.organization_id != organization.id
        ):
            raise ValidationError(
                {
                    "branch": "Selected branch does not belong to the selected organization.",  # noqa: E501
                },
            )

        return attrs


class BranchAdminInviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(max_length=255)
    father_name = serializers.CharField(max_length=255)
    grandfather_name = serializers.CharField(max_length=255)
    role_title = serializers.CharField(max_length=100)
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())

    EMAIL_VALIDATION_ERROR_MESSAGE = "A user with this email already exists."

    def validate(self, attrs):
        request = self.context.get("request")
        branch = attrs.get("branch")
        existing_user = User.objects.by_email(attrs["email"]).first()

        if existing_user is not None:
            if (
                existing_user.role != User.Role.BRANCH_ADMIN
                or existing_user.is_active
                or not BranchAdmin.objects.filter(user=existing_user).exists()
            ):
                raise serializers.ValidationError(
                    {"email": self.EMAIL_VALIDATION_ERROR_MESSAGE},
                )
            attrs["existing_user"] = existing_user

        if request and branch:
            if branch.organization.owner_id != request.user.id:
                raise serializers.ValidationError(
                    {"branch": "You can only manage branches in your organizations."},
                )
        return attrs


class BranchAdminCompleteInvitationSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(style={"input_type": "password"})
