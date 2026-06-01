from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from accounts.models import ApprovalLoginToken
from accounts.models import ParentLoginOTP
from accounts.models import User
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import serializers

from .auth import OrganizationLoginState
from .auth import get_organization_login_state

APPROVAL_MAGIC_LINK_EXPIRY = timedelta(hours=24)
APPROVAL_MAGIC_LINK_PATH = "organization-approval/{uid}/{token}"
PHONE_NUMBER_MIN_DIGITS = 10
PHONE_NUMBER_MAX_DIGITS = 15
PARENT_INVITATION_VERIFICATION_SALT = "parent-invitation-verification"


@dataclass(frozen=True)
class ApprovalMagicLink:
    path: str
    raw_token: str


@dataclass(frozen=True)
class InvitationLink:
    path: str
    full_url: str


def _hash_token_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def get_frontend_domain_for_user(user: User | None) -> str:
    role = getattr(user, "role", "")
    role_domains = getattr(settings, "FRONTEND_ROLE_DOMAINS", {})
    return str(role_domains.get(role) or settings.FRONTEND_DOMAIN)


def get_frontend_protocol_for_user(user: User | None) -> str:
    return str(settings.FRONTEND_PROTOCOL)


def build_frontend_url(path: str, *, user: User | None = None) -> str:
    domain = get_frontend_domain_for_user(user).rstrip("/")
    parsed_domain = urlsplit(domain)
    if parsed_domain.scheme and parsed_domain.netloc:
        base_url = domain
    else:
        base_url = f"{get_frontend_protocol_for_user(user)}://{domain}"
    return f"{base_url}/{path.lstrip('/')}"


def build_frontend_approval_magic_link(*, user: User, raw_token: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return APPROVAL_MAGIC_LINK_PATH.format(uid=uid, token=raw_token)


def create_invitation_link(*, user: User, path_template: str) -> InvitationLink:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = path_template.format(uid=uid, token=token)
    return InvitationLink(
        path=path,
        full_url=build_frontend_url(path, user=user),
    )


def create_parent_login_otp(*, user: User) -> str:
    now = timezone.now()
    ParentLoginOTP.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=now, updated_at=now)

    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    ParentLoginOTP.objects.create(
        user=user,
        phone_number=user.phone_number or "",
        code_hash=_hash_otp_code(raw_code),
        expires_at=now + timedelta(seconds=settings.PARENT_OTP_EXPIRY_SECONDS),
    )
    return raw_code


def create_parent_invitation_verification_token(*, user: User) -> str:
    payload = {
        "user_id": str(user.pk),
        "purpose": "parent-invitation-verification",
    }
    return signing.dumps(
        payload,
        salt=PARENT_INVITATION_VERIFICATION_SALT,
    )


def consume_parent_invitation_verification_token(
    *,
    user: User,
    raw_token: str,
) -> dict[str, str]:
    max_age = getattr(
        settings,
        "PARENT_INVITATION_VERIFICATION_TOKEN_MAX_AGE_SECONDS",
        15 * 60,
    )
    payload = signing.loads(
        raw_token,
        salt=PARENT_INVITATION_VERIFICATION_SALT,
        max_age=max_age,
    )

    if payload.get("purpose") != "parent-invitation-verification" or payload.get(
        "user_id",
    ) != str(user.pk):
        msg = "Invalid invitation verification token."
        raise signing.BadSignature(msg)

    return payload


@transaction.atomic
def consume_parent_login_otp(*, user: User, raw_code: str) -> ParentLoginOTP:
    otp = (
        ParentLoginOTP.objects.select_for_update()
        .filter(user=user, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None or otp.expires_at <= timezone.now():
        raise serializers.ValidationError(
            {"otp_code": "Invalid or expired OTP code."},
        )

    if otp.failed_attempts >= settings.PARENT_OTP_MAX_ATTEMPTS:
        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at", "updated_at"])
        raise serializers.ValidationError(
            {"otp_code": "Invalid or expired OTP code."},
        )

    expected_hash = _hash_otp_code(raw_code)
    if not constant_time_compare(otp.code_hash, expected_hash):
        otp.failed_attempts += 1
        update_fields = ["failed_attempts", "updated_at"]
        if otp.failed_attempts >= settings.PARENT_OTP_MAX_ATTEMPTS:
            otp.used_at = timezone.now()
            update_fields.append("used_at")
        otp.save(update_fields=update_fields)
        raise serializers.ValidationError(
            {"otp_code": "Invalid or expired OTP code."},
        )

    otp.used_at = timezone.now()
    otp.save(update_fields=["used_at", "updated_at"])
    return otp


def create_approval_magic_link(*, user: User) -> ApprovalMagicLink:
    secret = secrets.token_urlsafe(32)
    token_record = ApprovalLoginToken.objects.create(
        user=user,
        token_hash=_hash_token_secret(secret),
        expires_at=timezone.now() + APPROVAL_MAGIC_LINK_EXPIRY,
    )
    raw_token = f"{token_record.pk}.{secret}"
    return ApprovalMagicLink(
        path=build_frontend_approval_magic_link(user=user, raw_token=raw_token),
        raw_token=raw_token,
    )


def _parse_raw_token(raw_token: str) -> tuple[str, str]:
    token_id, separator, secret = raw_token.partition(".")
    if not separator or not token_id or not secret:
        raise serializers.ValidationError(
            {"token": "Invalid or expired approval link."},
        )
    return token_id, secret


@transaction.atomic
def consume_approval_magic_link(*, user: User, raw_token: str) -> ApprovalLoginToken:
    token_id, secret = _parse_raw_token(raw_token)

    try:
        token_record = ApprovalLoginToken.objects.select_for_update().get(
            pk=token_id,
            user=user,
        )
    except ApprovalLoginToken.DoesNotExist as err:
        raise serializers.ValidationError(
            {"token": "Invalid or expired approval link."},
        ) from err

    if token_record.used_at is not None or token_record.expires_at <= timezone.now():
        raise serializers.ValidationError(
            {"token": "Invalid or expired approval link."},
        )

    expected_hash = _hash_token_secret(secret)
    if not constant_time_compare(token_record.token_hash, expected_hash):
        raise serializers.ValidationError(
            {"token": "Invalid or expired approval link."},
        )

    if get_organization_login_state(user) != OrganizationLoginState.ALLOWED:
        raise serializers.ValidationError(
            {"token": "Invalid or expired approval link."},
        )

    token_record.used_at = timezone.now()
    token_record.save(update_fields=["used_at", "updated_at"])
    return token_record


def get_magic_link_email_context(
    *,
    user: User,
    raw_token: str,
    organization_name: str,
) -> dict[str, object]:
    return {
        "user": user,
        "organization_name": organization_name,
        "url": build_frontend_approval_magic_link(user=user, raw_token=raw_token),
        "domain": get_frontend_domain_for_user(user),
        "protocol": get_frontend_protocol_for_user(user),
    }
