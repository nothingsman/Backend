from accounts.models import User
from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from rest_framework import serializers


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
        return super().validate(attrs)
