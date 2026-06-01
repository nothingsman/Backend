from accounts.models import User
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers


def _validate_unique_contact_fields(
    attrs: dict[str, object],
    *,
    instance: User | None,
) -> None:
    email = str(attrs.get("email", "") or "").strip()
    phone_number = str(attrs.get("phone_number", "") or "").strip()

    if email:
        conflict = User.objects.by_email(email)
        if instance is not None:
            conflict = conflict.exclude(pk=instance.pk)
        if conflict.exists():
            raise serializers.ValidationError(
                {"email": ["A user with this email already exists."]},
            )

    if phone_number:
        try:
            conflict = User.objects.by_phone_number(phone_number)
        except ValueError as err:
            raise serializers.ValidationError(
                {"phone_number": [str(err)]},
            ) from err
        if instance is not None:
            conflict = conflict.exclude(pk=instance.pk)
        if conflict.exists():
            raise serializers.ValidationError(
                {"phone_number": ["A user with this phone number already exists."]},
            )


class UserSerializer(serializers.ModelSerializer[User]):
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
        _validate_unique_contact_fields(validated_data, instance=None)
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        _validate_unique_contact_fields(validated_data, instance=instance)
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserUpdateSerializer(serializers.ModelSerializer[User]):
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
        _validate_unique_contact_fields(validated_data, instance=instance)
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


class UserCreateSerializer(DjoserUserCreateSerializer):
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
        _validate_unique_contact_fields(attrs, instance=None)
        return super().validate(attrs)
