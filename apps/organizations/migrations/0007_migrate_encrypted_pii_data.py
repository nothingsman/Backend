from django.db import migrations

from core.services.pii import build_lookup_hash


def forwards(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")

    for organization in Organization.objects.all().iterator():
        organization.tin_number = organization.old_tin_number
        organization.tin_number_lookup_hash = build_lookup_hash(
            organization.old_tin_number,
            context="organizations.organization.tin_number",
        )
        organization.license_no = organization.old_license_no
        organization.license_no_lookup_hash = build_lookup_hash(
            organization.old_license_no,
            context="organizations.organization.license_no",
        )
        organization.client_full_name = organization.old_client_full_name
        organization.business_address = organization.old_business_address
        organization.business_phone_number = organization.old_business_phone_number
        organization.client_phone_number = organization.old_client_phone_number
        organization.verification_failure_reason = (
            organization.old_verification_failure_reason
        )
        organization.verified_license_no = organization.old_verified_license_no
        organization.verified_tin_number = organization.old_verified_tin_number
        organization.save(
            update_fields=[
                "tin_number",
                "tin_number_lookup_hash",
                "license_no",
                "license_no_lookup_hash",
                "client_full_name",
                "business_address",
                "business_phone_number",
                "client_phone_number",
                "verification_failure_reason",
                "verified_license_no",
                "verified_tin_number",
            ],
        )


def reverse(apps, schema_editor):
    Organization = apps.get_model("organizations", "Organization")

    for organization in Organization.objects.all().iterator():
        organization.old_tin_number = organization.tin_number
        organization.old_license_no = organization.license_no
        organization.old_client_full_name = organization.client_full_name
        organization.old_business_address = organization.business_address
        organization.old_business_phone_number = organization.business_phone_number
        organization.old_client_phone_number = organization.client_phone_number
        organization.old_verification_failure_reason = (
            organization.verification_failure_reason
        )
        organization.old_verified_license_no = organization.verified_license_no
        organization.old_verified_tin_number = organization.verified_tin_number
        organization.save(
            update_fields=[
                "old_tin_number",
                "old_license_no",
                "old_client_full_name",
                "old_business_address",
                "old_business_phone_number",
                "old_client_phone_number",
                "old_verification_failure_reason",
                "old_verified_license_no",
                "old_verified_tin_number",
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0006_add_encrypted_pii_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
