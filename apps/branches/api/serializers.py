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


class BranchAnalyticsTotalsSerializer(serializers.Serializer):
    active_students = serializers.IntegerField()
    active_teachers = serializers.IntegerField()
    active_branch_admins = serializers.IntegerField()


class BranchAcademicPerformanceAnnualPointSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    average_percentage = serializers.FloatField()


class BranchAcademicPerformanceQuarterlyPointSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    quarter = serializers.IntegerField()
    average_percentage = serializers.FloatField()


class BranchAcademicPerformanceSerializer(serializers.Serializer):
    annual = BranchAcademicPerformanceAnnualPointSerializer(many=True)
    quarterly = BranchAcademicPerformanceQuarterlyPointSerializer(many=True)


class BranchPerformanceRiskSerializer(serializers.Serializer):
    at_risk_students = serializers.IntegerField()
    percent = serializers.FloatField()


class BranchAttendanceTrendWeeklyPointSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    week = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


class BranchAttendanceTrendMonthlyPointSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


class BranchAttendanceTrendAnnualPointSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    attendance_rate = serializers.FloatField()


class BranchAttendanceTrendSerializer(serializers.Serializer):
    weekly = BranchAttendanceTrendWeeklyPointSerializer(many=True)
    monthly = BranchAttendanceTrendMonthlyPointSerializer(many=True)
    annual = BranchAttendanceTrendAnnualPointSerializer(many=True)


class BranchGradePerformanceSerializer(serializers.Serializer):
    grade_id = serializers.UUIDField()
    grade_name = serializers.CharField()
    student_count = serializers.IntegerField()
    performance_score = serializers.FloatField()


class BranchAnalyticsSerializer(serializers.Serializer):
    branch_id = serializers.UUIDField()
    totals = BranchAnalyticsTotalsSerializer()
    attendance_rate = serializers.FloatField()
    performance_risk = BranchPerformanceRiskSerializer()
    teacher_count = serializers.IntegerField()
    parent_linkage_percent = serializers.FloatField()
    attendance_trend = BranchAttendanceTrendSerializer()
    per_grade = BranchGradePerformanceSerializer(many=True)
    academic_performance_index = BranchAcademicPerformanceSerializer()


class BranchTopPerformanceRiskStudentSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    student_name = serializers.CharField()
    roll_no = serializers.CharField()
    grade_id = serializers.UUIDField(allow_null=True)
    grade_name = serializers.CharField(allow_null=True)
    risk_count = serializers.IntegerField()
    average_percentage = serializers.FloatField()
    latest_risk_at = serializers.DateTimeField()
