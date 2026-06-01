from __future__ import annotations

import base64
import hashlib
import hmac
import re
from functools import lru_cache
from typing import TYPE_CHECKING
from typing import Final

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from django.conf import settings

if TYPE_CHECKING:
    from datetime import date

PAYLOAD_PREFIX: Final[str] = "enc"
PAYLOAD_SEPARATOR: Final[str] = "::"
PHONE_NUMBER_MIN_DIGITS: Final[int] = 10
PHONE_NUMBER_MAX_DIGITS: Final[int] = 15


class EncryptionConfigurationError(RuntimeError):
    """Raised when field encryption is used without a valid key configuration."""


def normalize_email_value(value: str) -> str:
    return value.strip().casefold()


def normalize_phone_number(phone_number: str) -> str:
    stripped = phone_number.strip()
    if not stripped:
        message = "Phone number is required."
        raise ValueError(message)

    has_plus = stripped.startswith("+")
    digits = "".join(character for character in stripped if character.isdigit())
    if not digits:
        message = "Phone number must contain digits."
        raise ValueError(message)
    if len(digits) < PHONE_NUMBER_MIN_DIGITS or len(digits) > PHONE_NUMBER_MAX_DIGITS:
        message = "Phone number must contain between 10 and 15 digits."
        raise ValueError(message)

    return f"+{digits}" if has_plus else digits


def is_encrypted_payload(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(f"{PAYLOAD_PREFIX}{PAYLOAD_SEPARATOR}")
        and value.count(PAYLOAD_SEPARATOR) >= 2  # noqa: PLR2004
    )


@lru_cache(maxsize=1)
def _get_key_ring() -> dict[str, Fernet]:
    configured_keys = dict(getattr(settings, "PII_ENCRYPTION_KEYS", {}))
    key_ring: dict[str, Fernet] = {}
    for version, key in configured_keys.items():
        if not key:
            continue
        try:
            key_ring[version] = Fernet(key.encode("utf-8"))
        except (TypeError, ValueError) as err:
            message = f"Invalid encryption key configured for version '{version}'."
            raise EncryptionConfigurationError(message) from err

    if not key_ring:
        message = "No field encryption keys are configured."
        raise EncryptionConfigurationError(message)

    return key_ring


@lru_cache(maxsize=1)
def _get_lookup_hmac_key() -> bytes:
    configured_key = getattr(settings, "PII_LOOKUP_HMAC_KEY", "")
    if configured_key:
        return base64.urlsafe_b64decode(configured_key.encode("utf-8"))

    configured_keys = dict(getattr(settings, "PII_ENCRYPTION_KEYS", {}))
    if not configured_keys:
        message = "No field encryption keys are configured."
        raise EncryptionConfigurationError(message)

    configured_version = getattr(settings, "PII_LOOKUP_HMAC_KEY_VERSION", "")
    if configured_version:
        configured_key = configured_keys.get(configured_version)
        if not configured_key:
            message = (
                "Missing lookup HMAC key for configured version "
                f"'{configured_version}'."
            )
            raise EncryptionConfigurationError(message)
        return base64.urlsafe_b64decode(configured_key.encode("utf-8"))

    stable_version = min(configured_keys, key=_lookup_key_version_sort_key)
    configured_key = configured_keys.get(stable_version)
    if not configured_key:
        message = (
            "Missing field encryption key for stable lookup version "
            f"'{stable_version}'."
        )
        raise EncryptionConfigurationError(message)
    return base64.urlsafe_b64decode(configured_key.encode("utf-8"))


def _lookup_key_version_sort_key(version: str) -> tuple[int, int, str]:
    match = re.search(r"(\d+)$", version)
    if match is None:
        return (1, 0, version)
    return (0, int(match.group(1)), version)


def clear_encryption_caches() -> None:
    _get_key_ring.cache_clear()
    _get_lookup_hmac_key.cache_clear()


def encrypt_value(plaintext: str) -> str:
    key_ring = _get_key_ring()
    active_version = settings.PII_ENCRYPTION_ACTIVE_KEY_VERSION
    try:
        fernet = key_ring[active_version]
    except KeyError as err:
        message = f"Missing active field encryption key for version '{active_version}'."
        raise EncryptionConfigurationError(message) from err

    token = fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return PAYLOAD_SEPARATOR.join([PAYLOAD_PREFIX, active_version, token])


def decrypt_value(payload: str) -> str:
    if not is_encrypted_payload(payload):
        return payload

    _, version, token = payload.split(PAYLOAD_SEPARATOR, 2)
    key_ring = _get_key_ring()
    try:
        fernet = key_ring[version]
    except KeyError as err:
        message = f"Missing field encryption key for version '{version}'."
        raise EncryptionConfigurationError(message) from err

    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as err:
        message = (
            "Encrypted field value could not be decrypted with the configured key."
        )
        raise EncryptionConfigurationError(message) from err


def build_lookup_hash(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    digest = hmac.new(
        _get_lookup_hmac_key(),
        f"{context}:{normalized}".encode(),
        hashlib.sha256,
    )
    return digest.hexdigest()


def serialize_date_value(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
