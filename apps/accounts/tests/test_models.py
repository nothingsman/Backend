from __future__ import annotations

import base64
import hashlib

import pytest
from accounts.models import User
from accounts.tests.factories import UserFactory
from django.db import connection
from django.test import override_settings

from core.services import pii


def test_user_get_absolute_url(user: User):
    assert user.get_absolute_url() == f"/users/{user.pk}/"


@pytest.mark.django_db
def test_user_pii_is_encrypted_at_rest() -> None:
    user = UserFactory(
        email="encrypted@example.com",
        name="Encrypted Name",
        phone_number="+251911111999",
    )

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT email, name, phone_number FROM accounts_user WHERE id = %s",
            [str(user.pk)],
        )
        encrypted_email, encrypted_name, encrypted_phone = cursor.fetchone()

    assert encrypted_email != "encrypted@example.com"
    assert encrypted_name != "Encrypted Name"
    assert encrypted_phone != "+251911111999"
    assert "encrypted@example.com" not in encrypted_email


@pytest.mark.django_db
def test_user_blind_indexes_preserve_exact_lookup() -> None:
    user = UserFactory(
        email="lookup@example.com",
        phone_number="+251911111998",
    )

    assert User.objects.by_email("LOOKUP@example.com").get(pk=user.pk) == user
    assert User.objects.by_phone_number("+251911111998").get(pk=user.pk) == user


@pytest.mark.django_db
def test_user_lookup_hashes_remain_valid_across_key_rotation() -> None:
    key_v1 = base64.urlsafe_b64encode(hashlib.sha256(b"pii-v1").digest()).decode(
        "utf-8",
    )
    key_v2 = base64.urlsafe_b64encode(hashlib.sha256(b"pii-v2").digest()).decode(
        "utf-8",
    )

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_ENCRYPTION_KEYS={"v1": key_v1},
    ):
        pii.clear_encryption_caches()
        user = UserFactory(email="rotation@example.com")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v1": key_v1, "v2": key_v2},
    ):
        pii.clear_encryption_caches()
        user.refresh_from_db()

        assert user.email == "rotation@example.com"
        assert User.objects.by_email("rotation@example.com").get(pk=user.pk) == user

    pii.clear_encryption_caches()
