from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

LATEST_MIGRATION = ("accounts", "0006_normalize_user_phone_numbers")


def migrate_to(target):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(target)
    return executor


@pytest.mark.django_db(transaction=True)
def test_phone_number_migration_normalizes_existing_values():
    try:
        old_executor = migrate_to([("accounts", "0005_parentloginotp")])
        old_user_model = old_executor.loader.project_state(
            [("accounts", "0005_parentloginotp")],
        ).apps.get_model("accounts", "User")
        user = old_user_model.objects.create(
            email="migration-normalize@example.com",
            phone_number="251 911 111 121",
        )

        migrate_to([LATEST_MIGRATION])

        from accounts.models import User

        migrated_user = User.objects.get(pk=user.pk)
        assert migrated_user.phone_number == "+251911111121"
    finally:
        migrate_to([LATEST_MIGRATION])


@pytest.mark.django_db(transaction=True)
def test_phone_number_migration_fails_on_canonical_collision():
    old_user_model = None
    try:
        old_executor = migrate_to([("accounts", "0005_parentloginotp")])
        old_user_model = old_executor.loader.project_state(
            [("accounts", "0005_parentloginotp")],
        ).apps.get_model("accounts", "User")
        old_user_model.objects.create(
            email="collision-one@example.com",
            phone_number="+251911111122",
        )
        old_user_model.objects.create(
            email="collision-two@example.com",
            phone_number="251911111122",
        )

        with pytest.raises(RuntimeError, match="canonical collisions exist"):
            migrate_to([LATEST_MIGRATION])
    finally:
        if old_user_model is not None:
            old_user_model.objects.all().delete()
        migrate_to([LATEST_MIGRATION])
