import core.fields
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0005_rename_pii_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="tin_number",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=20,
                verbose_name="TIN Number",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="tin_number_lookup_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=64,
                null=True,
                verbose_name="TIN Number Lookup Hash",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="license_no",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=100,
                verbose_name="License Number",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="license_no_lookup_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                max_length=64,
                null=True,
                verbose_name="License Number Lookup Hash",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="client_full_name",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=255,
                verbose_name="Client Full Name",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="business_address",
            field=core.fields.EncryptedTextField(
                default="",
                verbose_name="Business Address",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="business_phone_number",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=50,
                verbose_name="Business Phone Number",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="client_phone_number",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=50,
                verbose_name="Client Phone Number",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="verification_failure_reason",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Verification Failure Reason",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="verified_license_no",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=100,
                verbose_name="Verified License Number",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="verified_tin_number",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=20,
                verbose_name="Verified TIN Number",
            ),
        ),
    ]
