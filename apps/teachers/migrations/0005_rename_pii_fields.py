from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("teachers", "0004_alter_teacher_employee_id_alter_teacher_joining_date"),
    ]

    operations = [
        migrations.RenameField(
            model_name="teacher",
            old_name="bio",
            new_name="old_bio",
        ),
        migrations.RenameField(
            model_name="teacherqualification",
            old_name="institution",
            new_name="old_institution",
        ),
        migrations.RenameField(
            model_name="teacherqualification",
            old_name="field_of_study",
            new_name="old_field_of_study",
        ),
    ]
