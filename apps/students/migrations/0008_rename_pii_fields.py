from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0007_studentacademicyearsection"),
    ]

    operations = [
        migrations.RenameField(
            model_name="parent",
            old_name="secondary_phone_number",
            new_name="old_secondary_phone_number",
        ),
        migrations.RenameField(
            model_name="parent",
            old_name="occupation",
            new_name="old_occupation",
        ),
        migrations.RenameField(
            model_name="parent",
            old_name="work_address",
            new_name="old_work_address",
        ),
        migrations.RenameField(
            model_name="parent",
            old_name="relationship_notes",
            new_name="old_relationship_notes",
        ),
        migrations.RenameField(
            model_name="parent",
            old_name="emergency_contact_name",
            new_name="old_emergency_contact_name",
        ),
        migrations.RenameField(
            model_name="parent",
            old_name="emergency_contact_phone",
            new_name="old_emergency_contact_phone",
        ),
        migrations.RenameField(
            model_name="student",
            old_name="first_name",
            new_name="old_first_name",
        ),
        migrations.RenameField(
            model_name="student",
            old_name="last_name",
            new_name="old_last_name",
        ),
        migrations.RenameField(
            model_name="student",
            old_name="date_of_birth",
            new_name="old_date_of_birth",
        ),
    ]
