import core.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0008_rename_pii_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="parent",
            name="secondary_phone_number",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=20,
                verbose_name="Secondary Phone Number",
            ),
        ),
        migrations.AddField(
            model_name="parent",
            name="occupation",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Occupation",
            ),
        ),
        migrations.AddField(
            model_name="parent",
            name="work_address",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Work Address",
            ),
        ),
        migrations.AddField(
            model_name="parent",
            name="relationship_notes",
            field=core.fields.EncryptedTextField(
                blank=True,
                verbose_name="Relationship Notes",
            ),
        ),
        migrations.AddField(
            model_name="parent",
            name="emergency_contact_name",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=255,
                verbose_name="Emergency Contact Name",
            ),
        ),
        migrations.AddField(
            model_name="parent",
            name="emergency_contact_phone",
            field=core.fields.EncryptedCharField(
                blank=True,
                max_length=50,
                verbose_name="Emergency Contact Phone",
            ),
        ),
        migrations.AddField(
            model_name="student",
            name="first_name",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=255,
                verbose_name="First Name",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="student",
            name="last_name",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=255,
                verbose_name="Last Name",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="student",
            name="date_of_birth",
            field=core.fields.EncryptedDateField(
                null=True,
                verbose_name="Date of Birth",
            ),
        ),
    ]
