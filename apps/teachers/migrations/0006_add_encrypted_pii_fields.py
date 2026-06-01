import core.fields
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("teachers", "0005_rename_pii_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacher",
            name="bio",
            field=core.fields.EncryptedTextField(blank=True, verbose_name="Bio"),
        ),
        migrations.AddField(
            model_name="teacherqualification",
            name="institution",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=255,
                verbose_name="Institution",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="teacherqualification",
            name="field_of_study",
            field=core.fields.EncryptedCharField(
                default="",
                max_length=255,
                verbose_name="Field of Study",
            ),
            preserve_default=False,
        ),
    ]
