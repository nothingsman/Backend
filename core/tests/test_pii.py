from __future__ import annotations

import base64
import hashlib
from datetime import date

import pytest
from django.test import override_settings

from core.fields import EncryptedCharField
from core.fields import EncryptedDateField
from core.services import pii


def build_fernet_key(label: str) -> str:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


@pytest.fixture(autouse=True)
def clear_pii_caches() -> None:
    pii.clear_encryption_caches()
    yield
    pii.clear_encryption_caches()


def test_encrypt_and_decrypt_round_trip_uses_active_version() -> None:
    key_v1 = build_fernet_key("pii-v1")
    key_v2 = build_fernet_key("pii-v2")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v1": key_v1, "v2": key_v2},
    ):
        payload = pii.encrypt_value("secret-value")

    assert payload.startswith("enc::v2::")
    assert pii.is_encrypted_payload(payload) is True

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v1": key_v1, "v2": key_v2},
    ):
        assert pii.decrypt_value(payload) == "secret-value"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("plain-text", False),
        ("enc::missing-parts", False),
        ("enc::v1", False),
        (None, False),
    ],
)
def test_is_encrypted_payload_rejects_malformed_values(
    value: str | None,
    expected: object,
) -> None:
    assert pii.is_encrypted_payload(value) is expected


@pytest.mark.parametrize("value", [None, "", "   "])
def test_build_lookup_hash_returns_none_for_blank_values(value: str | None) -> None:
    assert pii.build_lookup_hash(value, context="tests.lookup") is None


def test_build_lookup_hash_remains_stable_across_key_rotation() -> None:
    key_v1 = build_fernet_key("lookup-v1")
    key_v2 = build_fernet_key("lookup-v2")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_ENCRYPTION_KEYS={"v1": key_v1},
    ):
        original_hash = pii.build_lookup_hash(
            "lookup@example.com",
            context="accounts.user.email",
        )

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v1": key_v1, "v2": key_v2},
    ):
        rotated_hash = pii.build_lookup_hash(
            "lookup@example.com",
            context="accounts.user.email",
        )

    assert rotated_hash == original_hash


def test_build_lookup_hash_can_use_explicit_lookup_key_version() -> None:
    key_v1 = build_fernet_key("lookup-v1")
    key_v2 = build_fernet_key("lookup-v2")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_LOOKUP_HMAC_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v1": key_v1, "v2": key_v2},
    ):
        explicit_version_hash = pii.build_lookup_hash(
            "lookup@example.com",
            context="accounts.user.email",
        )

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v2": key_v2},
    ):
        expected_hash = pii.build_lookup_hash(
            "lookup@example.com",
            context="accounts.user.email",
        )

    assert explicit_version_hash == expected_hash


def test_encrypt_value_raises_for_invalid_configured_key() -> None:
    with (
        override_settings(
            PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
            PII_ENCRYPTION_KEYS={"v1": "not-a-valid-fernet-key"},
        ),
        pytest.raises(
            pii.EncryptionConfigurationError,
            match="Invalid encryption key configured",
        ),
    ):
        pii.encrypt_value("secret-value")


def test_decrypt_value_raises_when_payload_key_version_is_missing() -> None:
    key_v1 = build_fernet_key("decrypt-v1")
    key_v2 = build_fernet_key("decrypt-v2")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_ENCRYPTION_KEYS={"v1": key_v1},
    ):
        payload = pii.encrypt_value("secret-value")
        pii.clear_encryption_caches()

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v2",
        PII_ENCRYPTION_KEYS={"v2": key_v2},
    ):
        pii.clear_encryption_caches()
        with pytest.raises(
            pii.EncryptionConfigurationError,
            match="Missing field encryption key for version 'v1'",
        ):
            pii.decrypt_value(payload)


def test_decrypt_value_raises_for_invalid_token() -> None:
    key_v1 = build_fernet_key("invalid-token")

    with (
        override_settings(
            PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
            PII_ENCRYPTION_KEYS={"v1": key_v1},
        ),
        pytest.raises(
            pii.EncryptionConfigurationError,
            match="Encrypted field value could not be decrypted",
        ),
    ):
        pii.decrypt_value("enc::v1::not-a-valid-token")


def test_encrypted_char_field_round_trip_and_blank_handling() -> None:
    key_v1 = build_fernet_key("field-v1")
    field = EncryptedCharField(max_length=255)
    field.set_attributes_from_name("secret_value")

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_ENCRYPTION_KEYS={"v1": key_v1},
    ):
        stored_value = field.get_prep_value("top secret")
        assert stored_value != "top secret"
        assert pii.is_encrypted_payload(stored_value) is True
        assert field.to_python(stored_value) == "top secret"
        assert field.get_prep_value("") == ""
        assert field.get_prep_value(None) is None


def test_encrypted_date_field_round_trip() -> None:
    key_v1 = build_fernet_key("date-v1")
    field = EncryptedDateField()
    field.set_attributes_from_name("birth_date")
    expected_date = date(2020, 1, 2)

    with override_settings(
        PII_ENCRYPTION_ACTIVE_KEY_VERSION="v1",
        PII_ENCRYPTION_KEYS={"v1": key_v1},
    ):
        stored_value = field.get_prep_value(expected_date)
        assert stored_value is not None
        assert pii.is_encrypted_payload(stored_value) is True
        assert field.to_python(stored_value) == expected_date
        assert field.to_python(None) is None
