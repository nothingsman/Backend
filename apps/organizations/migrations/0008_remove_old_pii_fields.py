from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0007_migrate_encrypted_pii_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="old_tin_number",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_license_no",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_client_full_name",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_business_address",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_business_phone_number",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_client_phone_number",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_verification_failure_reason",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_verified_license_no",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="old_verified_tin_number",
        ),
    ]
