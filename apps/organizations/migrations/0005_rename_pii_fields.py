from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0004_port_business_license_image_to_media"),
    ]

    operations = [
        migrations.RenameField(
            model_name="organization",
            old_name="tin_number",
            new_name="old_tin_number",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="license_no",
            new_name="old_license_no",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="client_full_name",
            new_name="old_client_full_name",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="business_address",
            new_name="old_business_address",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="business_phone_number",
            new_name="old_business_phone_number",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="client_phone_number",
            new_name="old_client_phone_number",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="verification_failure_reason",
            new_name="old_verification_failure_reason",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="verified_license_no",
            new_name="old_verified_license_no",
        ),
        migrations.RenameField(
            model_name="organization",
            old_name="verified_tin_number",
            new_name="old_verified_tin_number",
        ),
    ]
