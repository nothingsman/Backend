from __future__ import annotations

import importlib

from core.services.pii import build_lookup_hash

migration = importlib.import_module(
    "accounts.migrations.0008_migrate_encrypted_pii_data",
)


def test_migrate_phone_number_normalizes_valid_legacy_values() -> None:
    phone_number, lookup_hash = migration.migrate_phone_number(" +251 911 111 999 ")

    assert phone_number == "+251911111999"
    assert lookup_hash == build_lookup_hash(
        "+251911111999",
        context="accounts.user.phone_number",
    )


def test_migrate_phone_number_preserves_invalid_legacy_values_without_lookup_hash() -> (
    None
):
    phone_number, lookup_hash = migration.migrate_phone_number(" 12345 ")

    assert phone_number == "12345"
    assert lookup_hash is None


def test_migrate_phone_number_treats_blank_legacy_values_as_missing() -> None:
    phone_number, lookup_hash = migration.migrate_phone_number("   ")

    assert phone_number is None
    assert lookup_hash is None
