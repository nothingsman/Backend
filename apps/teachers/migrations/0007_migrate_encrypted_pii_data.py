from django.db import migrations


def forwards(apps, schema_editor):
    Teacher = apps.get_model("teachers", "Teacher")
    TeacherQualification = apps.get_model("teachers", "TeacherQualification")

    for teacher in Teacher.objects.all().iterator():
        teacher.bio = teacher.old_bio
        teacher.save(update_fields=["bio"])

    for qualification in TeacherQualification.objects.all().iterator():
        qualification.institution = qualification.old_institution
        qualification.field_of_study = qualification.old_field_of_study
        qualification.save(update_fields=["institution", "field_of_study"])


def reverse(apps, schema_editor):
    Teacher = apps.get_model("teachers", "Teacher")
    TeacherQualification = apps.get_model("teachers", "TeacherQualification")

    for teacher in Teacher.objects.all().iterator():
        teacher.old_bio = teacher.bio
        teacher.save(update_fields=["old_bio"])

    for qualification in TeacherQualification.objects.all().iterator():
        qualification.old_institution = qualification.institution
        qualification.old_field_of_study = qualification.field_of_study
        qualification.save(update_fields=["old_institution", "old_field_of_study"])


class Migration(migrations.Migration):
    dependencies = [
        ("teachers", "0006_add_encrypted_pii_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse),
    ]
