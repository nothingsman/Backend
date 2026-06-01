from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.db import connection
from organizations.tests.factories import OrganizationFactory

if TYPE_CHECKING:
    from organizations.models import Organization


def test_organization_str(organization: Organization):
    assert str(organization) == organization.name


@pytest.mark.django_db
def test_organization_pii_is_encrypted_at_rest() -> None:
    organization = OrganizationFactory(
        tin_number="1234567890",
        license_no="LIC-123",
        client_full_name="Sample Owner",
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tin_number, license_no, client_full_name
            FROM organizations_organization
            WHERE id = %s
            """,
            [str(organization.pk)],
        )
        encrypted_tin, encrypted_license, encrypted_name = cursor.fetchone()

    assert encrypted_tin != "1234567890"
    assert encrypted_license != "LIC-123"
    assert encrypted_name != "Sample Owner"
