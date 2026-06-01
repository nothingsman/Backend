from accounts.models import User
from accounts.services import normalize_phone_number
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers


class UserPhoneNumberNormalizationMixin:
    phone_number_validation_error_message = (
        "A user with this phone number already exists."
    )

    def validate_phone_number(self, value: str) -> str:
        if not value:
            return value

        try:
            return normalize_phone_number(value)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

    def validate(self, attrs):
        attrs = super().validate(attrs)
        phone_number = attrs.get("phone_number")
        if not phone_number:
            return attrs

        phone_number_conflict = User.objects.filter(phone_number=phone_number)
        if getattr(self, "instance", None) is not None:
            phone_number_conflict = phone_number_conflict.exclude(
                pk=self.instance.pk,
            )
        if phone_number_conflict.exists():
            raise serializers.ValidationError(
                {"phone_number": self.phone_number_validation_error_message},
            )

        return attrs


class UserSerializer(
    UserPhoneNumberNormalizationMixin,
    serializers.ModelSerializer[User],
):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "father_name",
            "grandfather_name",
            "email",
            "phone_number",
            "address",
            "role",
            "password",
            "verified_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "verified_at", "created_at", "updated_at"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserUpdateSerializer(
    UserPhoneNumberNormalizationMixin,
    serializers.ModelSerializer[User],
):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = [
            "name",
            "father_name",
            "grandfather_name",
            "email",
            "phone_number",
            "address",
            "role",
            "password",
        ]

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserCreateSerializer(
    UserPhoneNumberNormalizationMixin,
    DjoserUserCreateSerializer,
):
    forbidden_signup_fields = frozenset(
        {
            "verified_at",
            "is_staff",
            "is_superuser",
            "is_active",
            "groups",
            "user_permissions",
        },
    )

    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = (
            "email",
            "id",
            "password",
            "name",
            "father_name",
            "grandfather_name",
            "phone_number",
            "address",
            "role",
        )

    def validate(self, attrs):
        forbidden_fields = self.forbidden_signup_fields.intersection(self.initial_data)
        if forbidden_fields:
            raise serializers.ValidationError(
                {
                    field: ["This field may not be set during signup."]
                    for field in sorted(forbidden_fields)
                },
            )
        return super().validate(attrs)
