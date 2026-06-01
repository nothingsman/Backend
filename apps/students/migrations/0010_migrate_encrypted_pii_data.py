from django.db import migrations


def forwards(apps, schema_editor):
    Parent = apps.get_model("students", "Parent")
    Student = apps.get_model("students", "Student")

    for parent in Parent.objects.all().iterator():
        parent.secondary_phone_number = parent.old_secondary_phone_number
        parent.occupation = parent.old_occupation
        parent.work_address = parent.old_work_address
        parent.relationship_notes = parent.old_relationship_notes
        parent.emergency_contact_name = parent.old_emergency_contact_name
        parent.emergency_contact_phone = parent.old_emergency_contact_phone
        parent.save(
            update_fields=[
                "secondary_phone_number",
                "occupation",
                "work_address",
                "relationship_notes",
                "emergency_contact_name",
                "emergency_contact_phone",
            ],
        )

    for student in Student.objects.all().iterator():
        student.first_name = student.old_first_name
        student.last_name = student.old_last_name
        student.date_of_birth = student.old_date_of_birth
        student.save(
            update_fields=[
                "first_name",
                "last_name",
                "date_of_birth",
            ],
        )


def reverse(apps, schema_editor):
    Parent = apps.get_model("students", "Parent")
    Student = apps.get_model("students", "Student")

    for parent in Parent.objects.all().iterator():
        parent.old_secondary_phone_number = parent.secondary_phone_number
        parent.old_occupation = parent.occupation
        parent.old_work_address = parent.work_address
        parent.old_relationship_notes = parent.relationship_notes
        parent.old_emergency_contact_name = parent.emergency_contact_name
        parent.old_emergency_contact_phone = parent.emergency_contact_phone
        parent.save(
            update_fields=[
                "old_secondary_phone_number",
                "old_occupation",
                "old_work_address",
                "old_relationship_notes",
                "old_emergency_contact_name",
                "old_emergency_contact_phone",
            ],
        )

    for student in Student.objects.all().iterator():
        student.old_first_name = student.first_name
        student.old_last_name = student.last_name
        student.old_date_of_birth = student.date_of_birth
        student.save(
            update_fields=[
                "old_first_name",
                "old_last_name",
                "old_date_of_birth",
            ],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0009_add_encrypted_pii_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
