from __future__ import annotations

from typing import TYPE_CHECKING

from accounts.models import User
from django.contrib.auth.models import update_last_login
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import exceptions
from rest_framework import serializers
from rest_framework_simplejwt.authentication import default_user_authentication_rule
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings
from students.models import Parent

from core.services.pii import normalize_phone_number

if TYPE_CHECKING:
    from django.http import HttpRequest

NO_ACTIVE_PARENT_ACCOUNT_MESSAGE = (
    "No active parent account was found for this phone number."
)
INCONSISTENT_PARENT_ACCOUNT_STATE_MESSAGE = "Parent account state is inconsistent. Please re-send the invitation or contact support."  # noqa: E501


def authenticate_phone_or_email_credentials(
    *,
    request: HttpRequest | None,
    email: str,
    phone_number: str,
    password: str,
) -> User | None:
    normalized_email = email.strip()
    normalized_phone = phone_number.strip()
    if normalized_phone:
        try:
            normalized_phone = normalize_phone_number(normalized_phone)
        except ValueError:
            return None

        user = (
            User.objects.by_phone_number(normalized_phone)
            .filter(
                role=User.Role.PARENT,
            )
            .first()
        )
        if user is None or not user.check_password(password):
            return None
        return user

    if not normalized_email:
        return None

    user = User.objects.by_email(normalized_email).first()
    if user is None or not user.check_password(password):
        return None
    return user


class ApprovalMagicLinkExchangeSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate_uid(self, value: str) -> str:
        try:
            user_id = force_str(urlsafe_base64_decode(value))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist) as err:
            message = "Invalid user ID."
            raise serializers.ValidationError(message) from err

        self.context["target_user"] = user
        return value

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        user = self.context.get("target_user")
        if user is None:
            raise serializers.ValidationError({"uid": "Invalid user ID."})

        if user.role != User.Role.ORGANIZATION:
            raise serializers.ValidationError(
                {"uid": "Invalid or expired approval link."},
            )

        return attrs


class ParentOTPRequestSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)

    def validate_phone_number(self, value: str) -> str:
        try:
            normalized = normalize_phone_number(value)
        except ValueError as err:
            raise serializers.ValidationError(str(err)) from err

        try:
            user = User.objects.by_phone_number(normalized).get(role=User.Role.PARENT)
        except User.DoesNotExist as err:
            raise serializers.ValidationError(
                NO_ACTIVE_PARENT_ACCOUNT_MESSAGE,
            ) from err

        try:
            parent_profile = user.parent_profile
        except Parent.DoesNotExist as err:
            raise serializers.ValidationError(
                NO_ACTIVE_PARENT_ACCOUNT_MESSAGE,
            ) from err

        if user.is_active != parent_profile.is_active:
            raise serializers.ValidationError(
                INCONSISTENT_PARENT_ACCOUNT_STATE_MESSAGE,
            )

        self.context["target_user"] = user
        return normalized


class ParentOTPVerifySerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    otp_code = serializers.RegexField(r"^\d{6}$")

    def validate_phone_number(self, value: str) -> str:
        request_serializer = ParentOTPRequestSerializer(
            data={"phone_number": value},
            context=self.context,
        )
        request_serializer.is_valid(raise_exception=True)
        return request_serializer.validated_data["phone_number"]


class ParentPhoneOrEmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(trim_whitespace=False)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        email_field = self.fields.get(self.username_field)
        if email_field is not None:
            email_field.required = False
            email_field.allow_blank = True

    def validate(
        self,
        attrs: dict[str, str],
    ) -> dict[str, str]:
        email = attrs.get("email", "")
        phone_number = attrs.get("phone_number", "")
        password = attrs.get("password", "")

        if not email.strip() and not phone_number.strip():
            raise serializers.ValidationError(
                {
                    "email": "Provide an email or phone number.",
                    "phone_number": "Provide a phone number or email.",
                },
            )

        user = authenticate_phone_or_email_credentials(
            request=self.context.get("request"),
            email=email,
            phone_number=phone_number,
            password=password,
        )
        if user is None or not default_user_authentication_rule(user):
            raise exceptions.AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        self.user = user

        refresh = self.get_token(user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)

        return data
