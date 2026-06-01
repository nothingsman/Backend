import core.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0010_migrate_encrypted_pii_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="student",
            name="date_of_birth",
            field=core.fields.EncryptedDateField(verbose_name="Date of Birth"),
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_secondary_phone_number",
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_occupation",
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_work_address",
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_relationship_notes",
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_emergency_contact_name",
        ),
        migrations.RemoveField(
            model_name="parent",
            name="old_emergency_contact_phone",
        ),
        migrations.RemoveField(
            model_name="student",
            name="old_first_name",
        ),
        migrations.RemoveField(
            model_name="student",
            name="old_last_name",
        ),
        migrations.RemoveField(
            model_name="student",
            name="old_date_of_birth",
        ),
    ]
