from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0011_remove_old_pii_fields"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="parent",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Parent",
                "verbose_name_plural": "Parents",
            },
        ),
    ]
