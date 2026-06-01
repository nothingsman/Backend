from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("teachers", "0007_migrate_encrypted_pii_data"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="teacher",
            name="old_bio",
        ),
        migrations.RemoveField(
            model_name="teacherqualification",
            name="old_institution",
        ),
        migrations.RemoveField(
            model_name="teacherqualification",
            name="old_field_of_study",
        ),
    ]
